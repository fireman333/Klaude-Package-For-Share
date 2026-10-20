#!/usr/bin/env Rscript
# ==============================================================================
# mice_driver.R -- MICE engine for the research-plan missing-data step.
#
# Called by missing_data.py:
#     Rscript mice_driver.R <spec.json> <result.json>
#
# Contract (see references/missing_data_protocol.md):
#   * The imputation model ALWAYS contains the outcome. For time-to-event that
#     means the event indicator PLUS mice::nelsonaalen() cumulative hazard --
#     never the raw survival time (White & Royston 2009). The raw time column is
#     carried through the frame only so the analysis model can be fitted; it is
#     switched off in the predictor matrix.
#   * Methods: continuous -> pmm, binary -> logreg, unordered -> polyreg,
#     ordered -> polr (auto-downgraded to logreg when only 2 levels exist).
#   * Pooling via mice::pool() (Rubin's rules, Barnard-Rubin df); df / RIV / FMI
#     are returned alongside every coefficient.
#   * Estimates are returned on the LOG scale. Exponentiation happens in Python.
#   * No plotting here -- convergence traces and observed-vs-imputed values are
#     returned as raw numbers so Python owns a single plotting style.
#
# This script never falls back to complete-case silently: any failure returns
# ok = FALSE with a message, and the Python caller turns that into [QC_BLOCKING].
# ==============================================================================

suppressWarnings(suppressMessages({
  ok_pkgs <- TRUE
  for (p in c("jsonlite", "mice", "survival")) {
    if (!requireNamespace(p, quietly = TRUE)) ok_pkgs <- FALSE
  }
}))

if (!ok_pkgs) {
  cat("{\"ok\":false,\"error\":\"Required R packages (jsonlite/mice/survival) are not installed\"}\n")
  quit(status = 1)
}

suppressWarnings(suppressMessages({
  library(jsonlite)
  library(mice)
  library(survival)
}))


# ------------------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------------------

bt <- function(x) paste0("`", x, "`")

`%||%` <- function(a, b) if (is.null(a)) b else a

as_chr_vec <- function(x) {
  if (is.null(x)) return(character(0))
  as.character(unlist(x, use.names = FALSE))
}

is_numeric_levels <- function(f) {
  lv <- levels(f)
  if (length(lv) == 0) return(FALSE)
  all(!is.na(suppressWarnings(as.numeric(lv))))
}

# Coerce one column to the type declared in the config.
coerce_var <- function(x, type, reference_level = NULL) {
  if (type == "continuous") {
    return(suppressWarnings(as.numeric(x)))
  }
  if (type == "ordinal") {
    num <- suppressWarnings(as.numeric(as.character(x)))
    if (all(is.na(num) | !is.na(num))) {
      # numeric codes -> order by value
      lv <- sort(unique(num[!is.na(num)]))
      if (length(lv) > 0) {
        return(factor(num, levels = lv, ordered = TRUE))
      }
    }
    lv <- sort(unique(as.character(x[!is.na(x)])))
    return(factor(as.character(x), levels = lv, ordered = TRUE))
  }
  # binary / categorical -> unordered factor, reference level first when given
  ch <- as.character(x)
  lv <- sort(unique(ch[!is.na(ch)]))
  if (!is.null(reference_level)) {
    ref <- as.character(reference_level)
    if (ref %in% lv) lv <- c(ref, setdiff(lv, ref))
  }
  factor(ch, levels = lv)
}

default_method <- function(type, n_levels) {
  if (type == "continuous") return("pmm")
  if (type == "binary") return("logreg")
  if (type == "ordinal") return(if (n_levels > 2) "polr" else "logreg")
  if (type == "categorical") return(if (n_levels > 2) "polyreg" else "logreg")
  "pmm"
}

# Auxiliary variables: infer type from the data itself.
infer_aux_type <- function(x) {
  num <- suppressWarnings(as.numeric(as.character(x)))
  if (!all(is.na(num[!is.na(x)]))) {
    u <- unique(num[!is.na(num)])
    if (length(u) <= 2) return("binary")
    return("continuous")
  }
  u <- unique(as.character(x[!is.na(x)]))
  if (length(u) <= 2) "binary" else "categorical"
}

tidy_fit <- function(fit, model_type) {
  s <- summary(fit)
  if (model_type == "cox") {
    co <- s$coefficients
    if (is.null(co) || nrow(co) == 0) return(list())
    est <- co[, "coef"]
    se <- co[, "se(coef)"]
    pv <- co[, ncol(co)]
  } else {
    co <- s$coefficients
    if (is.null(co) || nrow(co) == 0) return(list())
    keep <- rownames(co) != "(Intercept)"
    co <- co[keep, , drop = FALSE]
    if (nrow(co) == 0) return(list())
    est <- co[, "Estimate"]
    se <- co[, "Std. Error"]
    pv <- co[, 4]
  }
  out <- vector("list", length(est))
  for (i in seq_along(est)) {
    out[[i]] <- list(
      term = rownames(co)[i],
      estimate = unname(est[i]),
      std_error = unname(se[i]),
      p_value = unname(pv[i]),
      conf_low = unname(est[i] - 1.959964 * se[i]),
      conf_high = unname(est[i] + 1.959964 * se[i])
    )
  }
  out
}


# ------------------------------------------------------------------------------
# main worker
# ------------------------------------------------------------------------------

run_mice <- function(spec) {
  warns <- character(0)

  data_csv <- spec$data_csv
  if (!file.exists(data_csv)) stop(sprintf("data_csv not found: %s", data_csv))

  dat <- utils::read.csv(data_csv, check.names = FALSE, stringsAsFactors = FALSE,
                         na.strings = c("NA", "", "NaN", "nan"))
  if (nrow(dat) == 0) stop("Prepared analysis dataset has 0 rows")

  analysis_type <- spec$analysis_type
  mvars <- spec$model_variables
  if (length(mvars) == 0) stop("model_variables is empty")

  var_cols <- vapply(mvars, function(v) as.character(v$column), character(1))
  var_types <- vapply(mvars, function(v) as.character(v$type), character(1))
  names(var_types) <- var_cols
  var_scale <- setNames(lapply(mvars, function(v) v$scale %||% NULL), var_cols)
  var_ref <- setNames(lapply(mvars, function(v) v$reference_level %||% NULL), var_cols)

  aux_cols <- setdiff(as_chr_vec(spec$auxiliary_variables), var_cols)
  aux_cols <- aux_cols[aux_cols %in% names(dat)]

  missing_cols <- setdiff(var_cols, names(dat))
  if (length(missing_cols) > 0) {
    stop(sprintf("Columns missing from data: %s", paste(missing_cols, collapse = ", ")))
  }

  # ---- outcome columns ------------------------------------------------------
  time_col <- NULL; event_col <- NULL; outcome_col <- NULL
  if (identical(analysis_type, "cox")) {
    time_col <- as.character(spec$time_column)
    event_col <- as.character(spec$event_column)
    for (c0 in c(time_col, event_col)) {
      if (!c0 %in% names(dat)) stop(sprintf("Outcome column not found: %s", c0))
    }
    dat[[time_col]] <- suppressWarnings(as.numeric(dat[[time_col]]))
    dat[[event_col]] <- suppressWarnings(as.numeric(dat[[event_col]]))
    if (any(is.na(dat[[time_col]])) || any(is.na(dat[[event_col]]))) {
      stop("Outcome (time/event) contains missing values -- MI-then-delete required (protocol section 6)")
    }
    ev_levels <- sort(unique(dat[[event_col]]))
    if (length(ev_levels) > 2) {
      stop(sprintf("Event column '%s' has %d distinct values (%s) -- looks like competing risks; not supported (protocol section 6)",
                   event_col, length(ev_levels), paste(ev_levels, collapse = "/")))
    }
  } else {
    outcome_col <- as.character(spec$outcome_column)
    if (!outcome_col %in% names(dat)) stop(sprintf("Outcome column not found: %s", outcome_col))
    dat[[outcome_col]] <- suppressWarnings(as.numeric(dat[[outcome_col]]))
    if (any(is.na(dat[[outcome_col]]))) {
      stop("Outcome contains missing values -- MI-then-delete required (protocol section 6)")
    }
  }

  # ---- typed imputation frame ----------------------------------------------
  impdat <- data.frame(row.names = seq_len(nrow(dat)))
  roles <- list()
  types_used <- list()

  for (cn in var_cols) {
    impdat[[cn]] <- coerce_var(dat[[cn]], var_types[[cn]], var_ref[[cn]])
    roles[[cn]] <- "analysis"
    types_used[[cn]] <- var_types[[cn]]
  }
  for (cn in aux_cols) {
    tp <- infer_aux_type(dat[[cn]])
    impdat[[cn]] <- coerce_var(dat[[cn]], if (tp == "continuous") "continuous" else tp, NULL)
    roles[[cn]] <- "auxiliary"
    types_used[[cn]] <- tp
  }

  # Outcome goes INTO the imputation model (protocol 4.2).
  na_col <- NULL
  if (identical(analysis_type, "cox")) {
    impdat[[event_col]] <- as.numeric(dat[[event_col]])
    roles[[event_col]] <- "outcome_event"
    types_used[[event_col]] <- "binary"
    na_col <- "_na_cumhaz"
    tmp <- data.frame(.t = dat[[time_col]], .s = dat[[event_col]])
    impdat[[na_col]] <- as.numeric(mice::nelsonaalen(tmp, .t, .s))
    roles[[na_col]] <- "outcome_cumhaz"
    types_used[[na_col]] <- "continuous"
    # raw survival time: carried for the analysis model, NEVER a predictor
    impdat[[time_col]] <- as.numeric(dat[[time_col]])
    roles[[time_col]] <- "outcome_time_excluded"
    types_used[[time_col]] <- "continuous"
  } else {
    impdat[[outcome_col]] <- as.numeric(dat[[outcome_col]])
    roles[[outcome_col]] <- "outcome"
    types_used[[outcome_col]] <- "binary"
  }

  # drop zero-variance columns from the imputation frame (mice would log them)
  for (cn in names(impdat)) {
    v <- impdat[[cn]]
    nu <- length(unique(v[!is.na(v)]))
    if (nu < 2 && !identical(cn, time_col)) {
      if (roles[[cn]] == "auxiliary") {
        impdat[[cn]] <- NULL
        roles[[cn]] <- NULL
        types_used[[cn]] <- NULL
        aux_cols <- setdiff(aux_cols, cn)
        warns <- c(warns, sprintf("Auxiliary variable '%s' dropped (constant)", cn))
      } else {
        warns <- c(warns, sprintf("Variable '%s' is constant in this dataset", cn))
      }
    }
  }

  nmis <- vapply(impdat, function(x) sum(is.na(x)), numeric(1))

  # ---- method vector & predictor matrix ------------------------------------
  dry <- mice::mice(impdat, m = 1, maxit = 0, printFlag = FALSE)
  meth <- dry$method
  pred <- dry$predictorMatrix

  overrides <- spec$method_overrides %||% list()

  for (cn in names(impdat)) {
    if (nmis[[cn]] == 0) {
      meth[cn] <- ""            # protocol 4.3: never set a method on complete vars
      next
    }
    tp <- types_used[[cn]] %||% "continuous"
    nl <- if (is.factor(impdat[[cn]])) nlevels(droplevels(impdat[[cn]])) else Inf
    meth[cn] <- default_method(tp, nl)
    if (!is.null(overrides[[cn]])) meth[cn] <- as.character(overrides[[cn]])
  }

  if (!is.null(time_col) && time_col %in% colnames(pred)) {
    pred[, time_col] <- 0       # raw survival time excluded as a predictor
    meth[time_col] <- ""
  }
  diag(pred) <- 0

  m <- as.integer(spec$m)
  seed <- as.integer(spec$seed)
  maxit <- as.integer(spec$maxit)

  imputed_vars <- names(meth)[meth != "" & nmis[names(meth)] > 0]
  if (length(imputed_vars) == 0) {
    stop("No variable in the imputation model has missing values -- multiple imputation is not applicable")
  }

  imp <- mice::mice(impdat, m = m, maxit = maxit, method = meth,
                    predictorMatrix = pred, seed = seed, printFlag = FALSE)

  logged <- character(0)
  if (!is.null(imp$loggedEvents) && nrow(imp$loggedEvents) > 0) {
    le <- imp$loggedEvents
    logged <- unique(apply(le, 1, function(r)
      sprintf("it=%s im=%s meth=%s out=%s dep=%s",
              r[["it"]], r[["im"]], r[["meth"]], r[["out"]], r[["dep"]])))
    logged <- head(logged, 40)
  }

  # ---- post-imputation transform -------------------------------------------
  # Binary / ordinal factors return to their numeric codes so the analysis model
  # matches the rest of the pipeline (single linear term per variable); genuine
  # unordered categoricals stay factors so R builds the dummies.
  post_process <- function(d) {
    for (cn in var_cols) {
      tp <- var_types[[cn]]
      if (tp %in% c("binary", "ordinal")) {
        if (is.factor(d[[cn]]) && is_numeric_levels(d[[cn]])) {
          d[[cn]] <- as.numeric(as.character(d[[cn]]))
        }
      }
      sc <- var_scale[[cn]]
      if (!is.null(sc) && is.numeric(d[[cn]])) d[[cn]] <- d[[cn]] / as.numeric(sc)
    }
    d
  }

  term_vars <- vapply(var_cols, function(cn) bt(cn), character(1))
  rhs <- paste(term_vars, collapse = " + ")
  if (identical(analysis_type, "cox")) {
    fml <- stats::as.formula(sprintf("survival::Surv(%s, %s) ~ %s", bt(time_col), bt(event_col), rhs))
  } else {
    fml <- stats::as.formula(sprintf("%s ~ %s", bt(outcome_col), rhs))
  }

  fit_one <- function(d) {
    if (identical(analysis_type, "cox")) {
      survival::coxph(fml, data = d)
    } else {
      stats::glm(fml, data = d, family = stats::binomial())
    }
  }

  fits <- lapply(seq_len(m), function(i) fit_one(post_process(mice::complete(imp, i))))
  pooled <- mice::pool(fits)
  psum <- summary(pooled, conf.int = TRUE)
  pdf_ <- pooled$pooled

  get_col <- function(df, nms) {
    for (n in nms) if (n %in% names(df)) return(df[[n]])
    rep(NA_real_, nrow(df))
  }
  cl <- get_col(psum, c("conf.low", "2.5 %"))
  ch <- get_col(psum, c("conf.high", "97.5 %"))

  # The intercept is not a reported effect and has no complete-case counterpart
  # in tidy_fit(); dropping it here keeps Pooled and CC_vs_MI aligned.
  keep_rows <- which(as.character(psum$term) != "(Intercept)")

  pooled_out <- lapply(keep_rows, function(i) {
    tm <- as.character(psum$term[i])
    j <- match(tm, as.character(pdf_$term))
    list(
      term = tm,
      estimate = as.numeric(psum$estimate[i]),
      std_error = as.numeric(psum$std.error[i]),
      statistic = as.numeric(psum$statistic[i]),
      p_value = as.numeric(psum$p.value[i]),
      df = if (!is.na(j)) as.numeric(pdf_$df[j]) else NA_real_,
      fmi = if (!is.na(j)) as.numeric(pdf_$fmi[j]) else NA_real_,
      riv = if (!is.na(j)) as.numeric(pdf_$riv[j]) else NA_real_,
      lambda = if (!is.na(j)) as.numeric(pdf_$lambda[j]) else NA_real_,
      conf_low = as.numeric(cl[i]),
      conf_high = as.numeric(ch[i])
    )
  })

  # ---- complete-case reference fit -----------------------------------------
  cc_frame <- post_process(impdat)
  cc_needed <- c(var_cols, if (identical(analysis_type, "cox")) c(time_col, event_col) else outcome_col)
  cc_frame <- cc_frame[stats::complete.cases(cc_frame[, cc_needed, drop = FALSE]), , drop = FALSE]
  cc_n <- nrow(cc_frame)
  cc_events <- if (identical(analysis_type, "cox")) sum(cc_frame[[event_col]] == 1)
               else sum(cc_frame[[outcome_col]] == 1)
  cc_terms <- list()
  if (cc_n >= 10) {
    cc_fit <- try(fit_one(cc_frame), silent = TRUE)
    if (!inherits(cc_fit, "try-error")) {
      cc_terms <- tidy_fit(cc_fit, if (identical(analysis_type, "cox")) "cox" else "logistic")
    } else {
      warns <- c(warns, "Complete-case model failed to fit")
    }
  } else {
    warns <- c(warns, sprintf("Complete-case n = %d is too small to fit the reference model", cc_n))
  }

  mi_events <- if (identical(analysis_type, "cox")) sum(impdat[[event_col]] == 1)
               else sum(impdat[[outcome_col]] == 1)

  # ---- convergence traces ---------------------------------------------------
  cm <- imp$chainMean
  cv <- imp$chainVar
  conv_vars <- intersect(imputed_vars, dimnames(cm)[[1]])
  chain_mean <- list(); chain_sd <- list()
  for (v in conv_vars) {
    mm <- matrix(cm[v, , , drop = TRUE], nrow = maxit, ncol = m)
    vv <- matrix(cv[v, , , drop = TRUE], nrow = maxit, ncol = m)
    chain_mean[[v]] <- lapply(seq_len(m), function(j) as.numeric(mm[, j]))
    chain_sd[[v]] <- lapply(seq_len(m), function(j) sqrt(pmax(as.numeric(vv[, j]), 0)))
  }

  # ---- observed vs imputed distributions -----------------------------------
  cap <- as.integer(spec$max_dist_values %||% 4000)
  set.seed(seed)
  cap_vec <- function(x) if (length(x) > cap) sample(x, cap) else x

  dists <- list()
  for (v in imputed_vars) {
    obs_raw <- impdat[[v]]
    imp_raw <- imp$imp[[v]]
    if (is.null(imp_raw) || nrow(imp_raw) == 0) next
    if (is.factor(obs_raw)) {
      lv <- levels(obs_raw)
      obs_t <- table(factor(as.character(obs_raw[!is.na(obs_raw)]), levels = lv))
      imp_vals <- as.character(unlist(imp_raw, use.names = FALSE))
      imp_t <- table(factor(imp_vals, levels = lv))
      dists[[v]] <- list(kind = "categorical", levels = lv,
                         observed_counts = as.numeric(obs_t),
                         imputed_counts = as.numeric(imp_t),
                         n_imputations = m)
    } else {
      obs_v <- as.numeric(obs_raw[!is.na(obs_raw)])
      imp_v <- suppressWarnings(as.numeric(unlist(imp_raw, use.names = FALSE)))
      imp_v <- imp_v[!is.na(imp_v)]
      dists[[v]] <- list(kind = "numeric",
                         observed = cap_vec(obs_v),
                         imputed = cap_vec(imp_v),
                         observed_mean = mean(obs_v),
                         imputed_mean = if (length(imp_v)) mean(imp_v) else NA_real_,
                         observed_sd = stats::sd(obs_v),
                         imputed_sd = if (length(imp_v) > 1) stats::sd(imp_v) else NA_real_)
    }
  }

  # ---- imputation-model description ----------------------------------------
  predictor_list <- list()
  for (v in imputed_vars) {
    if (v %in% rownames(pred)) {
      predictor_list[[v]] <- colnames(pred)[pred[v, ] != 0]
    }
  }

  model_desc <- lapply(names(impdat), function(cn) {
    list(column = cn,
         role = roles[[cn]] %||% "unknown",
         type = types_used[[cn]] %||% "unknown",
         method = unname(meth[cn]),
         n_missing = unname(nmis[[cn]]),
         pct_missing = 100 * unname(nmis[[cn]]) / nrow(impdat),
         used_as_predictor = if (cn %in% colnames(pred)) any(pred[, cn] != 0) else FALSE)
  })

  list(
    ok = TRUE,
    error = NULL,
    versions = list(
      r = as.character(getRversion()),
      mice = as.character(utils::packageVersion("mice")),
      survival = as.character(utils::packageVersion("survival"))
    ),
    analysis_type = analysis_type,
    m = m, seed = seed, maxit = maxit,
    methods = as.list(meth[meth != ""]),
    imputed_variables = imputed_vars,
    imputation_model = model_desc,
    predictors = predictor_list,
    nmis = as.list(nmis),
    n_total = nrow(impdat),
    mi_events = mi_events,
    pooled = pooled_out,
    cc = list(n = cc_n, events = cc_events, terms = cc_terms),
    convergence = list(variables = conv_vars, maxit = maxit, m = m,
                       chain_mean = chain_mean, chain_sd = chain_sd),
    distributions = dists,
    logged_events = logged,
    warnings = warns
  )
}


# ------------------------------------------------------------------------------
# entry point
# ------------------------------------------------------------------------------

main <- function() {
  args <- commandArgs(trailingOnly = TRUE)
  if (length(args) < 2) {
    cat("Usage: Rscript mice_driver.R <spec.json> <result.json>\n")
    quit(status = 2)
  }
  in_path <- args[[1]]; out_path <- args[[2]]

  spec <- jsonlite::fromJSON(in_path, simplifyVector = TRUE,
                             simplifyDataFrame = FALSE, simplifyMatrix = FALSE)

  # R warnings are collected, not fatal: coxph / glm routinely warn about
  # convergence details that do not invalidate the pooled estimates. Only real
  # errors flip ok = FALSE (and the Python caller turns that into QC_BLOCKING).
  collected <- character(0)
  res <- withCallingHandlers(
    tryCatch(
      run_mice(spec),
      error = function(e) list(ok = FALSE, error = conditionMessage(e))
    ),
    warning = function(w) {
      collected <<- c(collected, conditionMessage(w))
      invokeRestart("muffleWarning")
    }
  )
  if (length(collected) > 0) {
    res$warnings <- unique(c(res$warnings, paste("R warning:", collected)))
  }

  jsonlite::write_json(res, out_path, auto_unbox = TRUE, digits = NA,
                       null = "null", na = "null", pretty = FALSE)
  if (isTRUE(res$ok)) quit(status = 0) else quit(status = 1)
}

main()
