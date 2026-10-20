#!/usr/bin/env Rscript
# survival_diagnostics.R
# Run 6 pre-flight survival diagnostics and emit a routing report.
#
# Usage:
#   Rscript survival_diagnostics.R <config.json>
#
# Config schema: see ../SKILL.md (JSON Config Schema).
# Output: diagnostic_report.json + diagnostic_report.md (+ figures/) in config$output_dir

suppressPackageStartupMessages({
  library(jsonlite)
  library(yaml)
})

# ---------- CLI ----------
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) stop("Usage: Rscript survival_diagnostics.R <config.json>")
cfg_path <- args[[1]]
if (!file.exists(cfg_path)) stop("Config not found: ", cfg_path)
cfg <- fromJSON(cfg_path, simplifyVector = FALSE)

# ---------- Thresholds ----------
# Resolve default thresholds.yaml relative to this script's location
script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
script_dir <- if (length(script_arg) > 0) {
  dirname(normalizePath(sub("^--file=", "", script_arg[1]), mustWork = FALSE))
} else {
  getwd()
}
default_thresholds_path <- file.path(script_dir, "..", "config", "thresholds.yaml")

thresholds_path <- if (!is.null(cfg$thresholds_file) && nzchar(cfg$thresholds_file)) {
  cfg$thresholds_file
} else {
  default_thresholds_path
}
if (!file.exists(thresholds_path)) {
  # Fall back to a built-in set if yaml is missing
  thresh <- list(
    competing_risks = list(min_event_types = 2L, cif_km_divergence_threshold = 0.05),
    recurrent_events = list(min_events_per_subject = 2L, min_pct_recurrent = 0.05),
    time_varying = list(immortal_time_ratio_threshold = 0.10, exposure_change_pct = 0.05),
    left_truncation = list(min_pct_truncated = 0.05, entry_time_variance_threshold = 0.01),
    informative_censoring = list(covariate_test_alpha = 0.05, min_censoring_rate = 0.10),
    clustering = list(icc_threshold = 0.01, min_clusters = 3L, min_cluster_size = 5L)
  )
} else {
  thresh <- yaml::read_yaml(thresholds_path)
}

# ---------- Reproducibility ----------
# Null-coalescing helper (avoid rlang dependency)
`%||%` <- function(a, b) if (is.null(a)) b else a
set.seed(as.integer(cfg$seed %||% 42L))

# ---------- Output dir ----------
out_dir <- cfg$output_dir
if (is.null(out_dir) || out_dir == "") stop("config$output_dir is required")
fig_dir <- file.path(out_dir, "figures")
dir.create(fig_dir, recursive = TRUE, showWarnings = FALSE)

# ---------- Load data ----------
data_file <- cfg$data_file
if (is.null(data_file) || !file.exists(data_file)) stop("data_file not found: ", data_file)

ext <- tolower(tools::file_ext(data_file))
df <- if (ext %in% c("xlsx", "xls")) {
  if (!requireNamespace("readxl", quietly = TRUE)) stop("readxl required for xlsx input")
  as.data.frame(readxl::read_excel(data_file))
} else if (ext %in% c("csv", "txt", "tsv")) {
  if (!requireNamespace("readr", quietly = TRUE)) stop("readr required for csv input")
  as.data.frame(readr::read_csv(data_file, show_col_types = FALSE))
} else if (ext == "rds") {
  readRDS(data_file)
} else {
  stop("Unsupported file extension: ", ext)
}

# ---------- Apply filters ----------
apply_filter <- function(df, f) {
  col <- f$column; op <- f$operator; v <- f$value
  if (!col %in% names(df)) stop("Filter column not found: ", col)
  x <- df[[col]]
  keep <- switch(op,
    "=="  = x == v,
    "!="  = x != v,
    ">"   = x >  v,
    ">="  = x >= v,
    "<"   = x <  v,
    "<="  = x <= v,
    "in"  = x %in% unlist(v),
    "not_in" = !(x %in% unlist(v)),
    stop("Unknown operator: ", op))
  df[which(keep), , drop = FALSE]
}
if (!is.null(cfg$filters) && length(cfg$filters) > 0) {
  for (f in cfg$filters) df <- apply_filter(df, f)
}
cat(sprintf("Loaded data: %d rows x %d cols\n", nrow(df), ncol(df)))

# ---------- Resolve columns ----------
time_col  <- cfg$time_column
event_col <- cfg$event_column
id_col    <- cfg$id_column
entry_col <- cfg$entry_column
cluster_col <- cfg$cluster_column
exposure_col <- cfg$exposure_column
tstart_col <- cfg$tstart_column
tstop_col  <- cfg$tstop_column

required_cols <- c(time_col, event_col)
missing_req <- setdiff(required_cols, names(df))
if (length(missing_req) > 0) stop("Required columns missing: ", paste(missing_req, collapse = ", "))

# Structural columns to exclude from covariate-level tests
structural_cols <- unique(c(
  time_col, event_col, id_col, entry_col, cluster_col, exposure_col, tstart_col, tstop_col
))
structural_cols <- structural_cols[!is.null(structural_cols) & structural_cols != ""]

candidate_covariates <- cfg$candidate_covariates
if (is.null(candidate_covariates) || length(candidate_covariates) == 0) {
  candidate_covariates <- setdiff(names(df), structural_cols)
} else {
  candidate_covariates <- intersect(unlist(candidate_covariates), names(df))
}

# ---------- Check 1: Competing Risks ----------
check_competing_risks <- function() {
  t_cr <- thresh$competing_risks
  ev <- df[[event_col]]
  event_codes <- sort(unique(ev[!is.na(ev) & ev != 0]))
  n_et <- length(event_codes)
  counts <- as.list(table(ev, useNA = "no"))
  names(counts) <- as.character(names(table(ev)))

  detected <- n_et >= t_cr$min_event_types
  divergence <- NA_real_

  if (detected && requireNamespace("cmprsk", quietly = TRUE) &&
      requireNamespace("survival", quietly = TRUE)) {
    ftime <- df[[time_col]]
    fstatus <- ev
    valid <- !is.na(ftime) & !is.na(fstatus) & ftime > 0
    ftime <- ftime[valid]; fstatus <- fstatus[valid]

    cif_fit <- tryCatch(cmprsk::cuminc(ftime, fstatus),
                        error = function(e) { message("[DIAG_WARNING] cuminc failed: ", e$message); NULL })
    if (!is.null(cif_fit)) {
      # P-6 audit fix (2026-05-08, sd-stat-02): primary event code now requires
      # explicit declaration. Previously took event_codes[1] silently — if user's
      # data uses 0=censor / 2=primary / 1=competing (non-default order), the
      # diagnostic would treat the competing event as primary and route data to
      # KM (wrong). Require config$primary_event_code; fall back with WARNING
      # only if multi-code with no explicit mapping.
      primary <- if (!is.null(cfg$primary_event_code)) {
        as.numeric(cfg$primary_event_code)
      } else if (length(event_codes) == 1L) {
        event_codes[1]  # Single non-zero code — unambiguous
      } else {
        message("[DIAG_WARNING] primary_event_code not declared but ",
                length(event_codes), " non-zero event codes present (",
                paste(event_codes, collapse = ", "), "). ",
                "Defaulting to lowest code = ", event_codes[1],
                "; if this is wrong, declare primary_event_code explicitly in the config.")
        event_codes[1]
      }
      if (!primary %in% event_codes) {
        stop("[FATAL] primary_event_code = ", primary,
             " not found in data event codes (", paste(event_codes, collapse = ", "),
             "). Check config or recode the event column.")
      }
      km_status <- ifelse(fstatus == primary, 1L, 0L)
      km_fit <- survival::survfit(survival::Surv(ftime, km_status) ~ 1)

      cif_name <- grep(paste0(" ", primary, "$"), names(cif_fit), value = TRUE)
      if (length(cif_name) == 0) cif_name <- names(cif_fit)[1]
      cif_entry <- cif_fit[[cif_name[1]]]
      if (!is.null(cif_entry)) {
        km_fun <- stepfun(km_fit$time, c(1, km_fit$surv))
        one_minus_km <- 1 - km_fun(cif_entry$time)
        divergence <- suppressWarnings(max(abs(cif_entry$est - one_minus_km), na.rm = TRUE))
      }
    }
    detected <- detected && !is.na(divergence) && divergence > t_cr$cif_km_divergence_threshold
  } else if (detected) {
    message("[DIAG_WARNING] cmprsk not installed — cannot compute CIF-KM divergence; flagging based on event-type count only.")
  }

  if (detected) {
    tryCatch({
      png(file.path(fig_dir, "competing_risks_events.png"), width = 800, height = 600, res = 150)
      barplot(table(ev), col = grDevices::hcl.colors(length(unique(ev)), "Set 2"),
              main = "Event Type Distribution", xlab = "Event Code (0 = censored)",
              ylab = "Count", border = NA)
      dev.off()
    }, error = function(e) message("[DIAG_WARNING] figure failed: ", e$message))
  }

  list(detected = detected,
       n_event_types = n_et,
       event_types = as.list(event_codes),
       cif_km_divergence = if (is.na(divergence)) NULL else round(divergence, 6),
       event_counts = counts)
}

# ---------- Check 2: Recurrent Events ----------
check_recurrent_events <- function() {
  t_re <- thresh$recurrent_events
  if (is.null(id_col) || id_col == "" || !id_col %in% names(df)) {
    message("[DIAG_WARNING] id_column not provided — skipping recurrent-events check.")
    return(list(detected = NA, skipped = TRUE, reason = "id_column missing"))
  }
  ev <- df[[event_col]]
  ids <- df[[id_col]]
  event_mask <- !is.na(ev) & ev != 0
  per_subj <- tapply(event_mask, ids, sum)
  per_subj <- per_subj[!is.na(per_subj)]
  if (length(per_subj) == 0) return(list(detected = FALSE, reason = "no subjects"))

  max_ev <- max(per_subj)
  n_rec <- sum(per_subj >= t_re$min_events_per_subject)
  pct_rec <- n_rec / length(per_subj)
  detected <- pct_rec >= t_re$min_pct_recurrent

  if (detected) {
    tryCatch({
      png(file.path(fig_dir, "recurrent_events_histogram.png"), width = 800, height = 600, res = 150)
      hist(per_subj, breaks = seq(-0.5, max_ev + 0.5, by = 1), col = "steelblue",
           border = "white", main = "Events per Subject",
           xlab = "Number of Events", ylab = "Subjects")
      abline(v = t_re$min_events_per_subject - 0.5, col = "red", lty = 2)
      dev.off()
    }, error = function(e) message("[DIAG_WARNING] figure failed: ", e$message))
  }

  list(detected = detected,
       max_events_per_subject = as.integer(max_ev),
       pct_recurrent = round(pct_rec, 6),
       n_subjects_recurrent = as.integer(n_rec),
       n_subjects_total = length(per_subj))
}

# ---------- Check 3: Time-Varying Exposure ----------
check_time_varying <- function() {
  t_tv <- thresh$time_varying
  has_cp <- !is.null(tstart_col) && !is.null(tstop_col) &&
            tstart_col %in% names(df) && tstop_col %in% names(df)
  if (!has_cp) {
    return(list(detected = FALSE, skipped = TRUE,
                reason = "No counting-process data (tstart/tstop). Time-varying exposure cannot be assessed without multi-row-per-subject format."))
  }
  if (is.null(id_col) || !id_col %in% names(df)) {
    return(list(detected = NA, skipped = TRUE, reason = "id_column required"))
  }

  ids <- df[[id_col]]
  dups <- ids[duplicated(ids)]
  multi_subjs <- unique(dups)
  if (length(multi_subjs) == 0) {
    return(list(detected = FALSE, reason = "No subjects with multiple intervals"))
  }

  tv_vars <- character(0)
  if (!is.null(exposure_col) && exposure_col %in% names(df)) {
    # Only check the declared exposure column (fast path)
    vals <- df[[exposure_col]]
    per_id <- tapply(vals[ids %in% multi_subjs], ids[ids %in% multi_subjs],
                     function(x) length(unique(x[!is.na(x)])))
    if (any(per_id > 1, na.rm = TRUE)) tv_vars <- exposure_col
  } else {
    # Scan candidate covariates
    for (v in intersect(candidate_covariates, names(df))) {
      vals <- df[[v]]
      per_id <- tapply(vals[ids %in% multi_subjs], ids[ids %in% multi_subjs],
                       function(x) length(unique(x[!is.na(x)])))
      if (any(per_id > 1, na.rm = TRUE)) tv_vars <- c(tv_vars, v)
    }
  }

  detected <- length(tv_vars) > 0
  immortal_ratio <- 0; pct_switchers <- 0; risk <- "low"

  if (detected) {
    # Use first binary time-varying column for immortal time calculation
    v <- tv_vars[1]
    vals <- df[[v]]
    if (is.numeric(vals) && all(vals %in% c(0, 1, NA))) {
      switchers <- character(0)
      for (sid in multi_subjs) {
        sub <- df[ids == sid, , drop = FALSE]
        sub <- sub[order(sub[[tstart_col]]), ]
        vv <- sub[[v]]
        if (length(vv) >= 2 && isTRUE(vv[1] == 0) && any(vv == 1, na.rm = TRUE)) {
          switchers <- c(switchers, as.character(sid))
        }
      }
      if (length(switchers) > 0) {
        pct_switchers <- length(switchers) / length(unique(ids))
        total_pt <- sum(df[[tstop_col]] - df[[tstart_col]], na.rm = TRUE)
        pre_pt <- 0
        for (sid in switchers) {
          sub <- df[ids == sid, , drop = FALSE]
          sub <- sub[order(sub[[tstart_col]]), ]
          idx <- which(sub[[v]] == 1)[1]
          if (!is.na(idx) && idx > 1) {
            pre <- sub[1:(idx - 1), , drop = FALSE]
            pre_pt <- pre_pt + sum(pre[[tstop_col]] - pre[[tstart_col]], na.rm = TRUE)
          }
        }
        immortal_ratio <- if (total_pt > 0) pre_pt / total_pt else 0

        if (immortal_ratio > t_tv$immortal_time_ratio_threshold &&
            pct_switchers > t_tv$exposure_change_pct) {
          risk <- "high"
        } else if (immortal_ratio > t_tv$immortal_time_ratio_threshold / 2 ||
                   pct_switchers > t_tv$exposure_change_pct / 2) {
          risk <- "medium"
        }
      }
    }
    # Final detection requires either threshold breached
    detected <- immortal_ratio > t_tv$immortal_time_ratio_threshold ||
                pct_switchers >= t_tv$exposure_change_pct
  }

  list(detected = detected,
       time_varying_variables = as.list(tv_vars),
       immortal_time_ratio = round(immortal_ratio, 6),
       pct_switchers = round(pct_switchers, 6),
       immortal_time_risk = risk)
}

# ---------- Check 4: Left Truncation ----------
check_left_truncation <- function() {
  t_lt <- thresh$left_truncation
  if (is.null(entry_col) || entry_col == "") {
    return(list(detected = FALSE, skipped = TRUE,
                reason = "entry_column not provided — left truncation assumed absent"))
  }
  if (!entry_col %in% names(df)) {
    return(list(detected = NA, skipped = TRUE, reason = paste("entry_column not found:", entry_col)))
  }

  et <- df[[entry_col]]
  trunc <- !is.na(et) & et > 0
  pct_tr <- sum(trunc) / sum(!is.na(et))
  med_ent <- median(et, na.rm = TRUE)
  max_ent <- suppressWarnings(max(et, na.rm = TRUE))

  detected <- pct_tr >= t_lt$min_pct_truncated

  informative_p <- NULL
  if (detected && sum(trunc) >= 5) {
    numeric_covs <- intersect(candidate_covariates, names(df))
    numeric_covs <- numeric_covs[sapply(numeric_covs, function(v) is.numeric(df[[v]]))]
    numeric_covs <- head(numeric_covs, 10)
    if (length(numeric_covs) > 0) {
      fml <- as.formula(paste(entry_col, "~", paste(numeric_covs, collapse = " + ")))
      tryCatch({
        fit <- lm(fml, data = df)
        ft <- summary(fit)$fstatistic
        if (!is.null(ft) && length(ft) == 3) {
          informative_p <- round(as.numeric(pf(ft[1], ft[2], ft[3], lower.tail = FALSE)), 6)
        }
      }, error = function(e) message("[DIAG_WARNING] informative-truncation test failed: ", e$message))
    }
  }

  list(detected = detected,
       pct_truncated = round(pct_tr, 6),
       median_entry_time = round(as.numeric(med_ent), 4),
       max_entry_time = round(as.numeric(max_ent), 4),
       informative_test_pvalue = informative_p)
}

# ---------- Check 5: Informative Censoring ----------
check_informative_censoring <- function() {
  t_ic <- thresh$informative_censoring

  # If counting-process, reduce to last row per subject
  analysis_df <- df
  if (!is.null(tstart_col) && tstart_col %in% names(df) &&
      !is.null(id_col) && id_col %in% names(df)) {
    # Sort by (id, tstart) so "last row" is deterministic (Bug fix: previously
    # relied on input row order, which produced unpredictable results).
    ord <- order(df[[id_col]], df[[tstart_col]])
    sorted_df <- df[ord, , drop = FALSE]
    ids <- sorted_df[[id_col]]
    last_idx <- unlist(tapply(seq_len(nrow(sorted_df)), ids, function(x) x[length(x)]))
    analysis_df <- sorted_df[last_idx, , drop = FALSE]
  }

  ev <- analysis_df[[event_col]]
  censored <- !is.na(ev) & ev == 0
  cens_rate <- mean(censored, na.rm = TRUE)

  covariate_tests <- list()
  alpha <- t_ic$covariate_test_alpha

  if (cens_rate >= t_ic$min_censoring_rate) {
    for (v in intersect(candidate_covariates, names(analysis_df))) {
      vals <- analysis_df[[v]]
      if (all(is.na(vals))) next
      tr <- list(variable = v, test = NA_character_, p_value = NA_real_, significant = FALSE)
      tryCatch({
        if (is.numeric(vals)) {
          cv <- analysis_df[[v]][censored]; ev2 <- analysis_df[[v]][!censored]
          cv <- cv[!is.na(cv)]; ev2 <- ev2[!is.na(ev2)]
          if (length(cv) >= 2 && length(ev2) >= 2) {
            wt <- suppressWarnings(wilcox.test(cv, ev2))
            tr$test <- "wilcoxon"; tr$p_value <- round(wt$p.value, 6)
            tr$significant <- isTRUE(wt$p.value < alpha)
          }
        } else if (is.factor(vals) || is.character(vals)) {
          tbl <- table(analysis_df[[v]], censored)
          if (nrow(tbl) >= 2 && ncol(tbl) == 2 && all(rowSums(tbl) > 0)) {
            ct <- suppressWarnings(chisq.test(tbl, simulate.p.value = (min(tbl) < 5)))
            tr$test <- "chi_square"; tr$p_value <- round(ct$p.value, 6)
            tr$significant <- isTRUE(ct$p.value < alpha)
          }
        }
      }, error = function(e) message("[DIAG_WARNING] test failed for ", v, ": ", e$message))
      covariate_tests <- c(covariate_tests, list(tr))
    }
  }

  # BH-FDR correction across covariate tests (>=3 tests); attach p_adj.
  raw_p <- sapply(covariate_tests, function(x) x$p_value)
  if (length(covariate_tests) >= 3 && any(!is.na(raw_p))) {
    adj_p <- p.adjust(raw_p, method = "BH")
    for (i in seq_along(covariate_tests)) {
      covariate_tests[[i]]$p_adj <- if (is.na(adj_p[i])) NA_real_ else round(adj_p[i], 6)
      covariate_tests[[i]]$significant <- isTRUE(covariate_tests[[i]]$p_adj < alpha)
    }
    min_p <- suppressWarnings(min(adj_p, na.rm = TRUE))
    if (!is.finite(min_p)) min_p <- NA_real_
  } else {
    for (i in seq_along(covariate_tests)) covariate_tests[[i]]$p_adj <- NA_real_
    p_values <- raw_p[!is.na(raw_p)]
    min_p <- if (length(p_values) > 0) min(p_values) else NA_real_
  }
  detected <- !is.na(min_p) && min_p < alpha && cens_rate >= t_ic$min_censoring_rate

  list(detected = detected,
       censoring_rate = round(cens_rate, 6),
       covariate_tests = covariate_tests,
       min_p_value = if (is.na(min_p)) NULL else round(min_p, 6),
       p_adjust_method = if (length(covariate_tests) >= 3) "BH" else "none")
}

# ---------- Check 6: Clustering ----------
check_clustering <- function() {
  t_cl <- thresh$clustering
  if (is.null(cluster_col) || cluster_col == "") {
    return(list(detected = FALSE, skipped = TRUE,
                reason = "cluster_column not provided"))
  }
  if (!cluster_col %in% names(df)) {
    return(list(detected = NA, skipped = TRUE, reason = paste("cluster_column not found:", cluster_col)))
  }

  cvals <- df[[cluster_col]]
  valid <- !is.na(cvals)
  cvals <- cvals[valid]
  sizes <- table(cvals)
  n_cl <- length(sizes)
  mean_sz <- mean(sizes)

  detected <- n_cl >= t_cl$min_clusters && mean_sz >= t_cl$min_cluster_size
  icc <- 0; recommendation <- "none"

  if (detected) {
    tvals <- df[[time_col]][valid]
    tryCatch({
      aov_fit <- aov(tvals ~ factor(cvals))
      ms <- summary(aov_fit)[[1]]
      ms_b <- ms["Mean Sq"][1, 1]; ms_w <- ms["Mean Sq"][2, 1]
      # n0: unbalanced design (Searle 1971, eq 9.5.3)
      # n_i: per-cluster sizes; k: n distinct clusters; N: total
      n_i <- as.numeric(sizes); k <- n_cl; N <- sum(n_i)
      n0 <- if (k > 1) (1 / (k - 1)) * (N - sum(n_i^2) / N) else mean_sz
      icc <- (ms_b - ms_w) / (ms_b + (n0 - 1) * ms_w)
      icc <- max(0, icc, na.rm = TRUE)
    }, error = function(e) {
      message("[DIAG_WARNING] ICC ANOVA failed: ", e$message)
    })

    detected <- icc > t_cl$icc_threshold && n_cl >= t_cl$min_clusters && mean_sz >= t_cl$min_cluster_size
    recommendation <- if (icc > t_cl$icc_threshold) "frailty" else "robust_se"
  }

  list(detected = detected,
       cluster_variable = cluster_col,
       n_clusters = as.integer(n_cl),
       mean_cluster_size = round(as.numeric(mean_sz), 2),
       icc = round(as.numeric(icc), 6),
       recommendation = recommendation)
}

# ---------- Run all 6 ----------
cat("Running 6 diagnostic checks...\n")
checks <- list(
  competing_risks       = check_competing_risks(),
  recurrent_events      = check_recurrent_events(),
  time_varying          = check_time_varying(),
  left_truncation       = check_left_truncation(),
  informative_censoring = check_informative_censoring(),
  clustering            = check_clustering()
)

# Emit pipeline-friendly flags
is_detected <- function(nm) isTRUE(checks[[nm]]$detected)
for (nm in names(checks)) {
  if (is_detected(nm)) message(sprintf("[DIAG_FLAG] %s detected", nm))
}

# ---------- Routing (bundled skill names) ----------
primary <- "kaplan-meier"
secondary <- character(0)
sensitivity <- character(0)

if (is_detected("competing_risks")) {
  primary <- "competing-risk"
  secondary <- c(secondary, "kaplan-meier (as reference only)")
}
if (is_detected("recurrent_events")) {
  secondary <- c(secondary, "OUT_OF_SCOPE: recurrent-event / multi-state model (no user skill covers this)")
}
if (is_detected("time_varying")) {
  secondary <- c(secondary, "extended Cox with tt() or counting-process format (manual implementation — no built-in skill)")
  if (checks$time_varying$immortal_time_risk %in% c("medium", "high")) {
    sensitivity <- c(sensitivity, "landmark analysis")
  }
}
if (is_detected("left_truncation")) {
  sensitivity <- c(sensitivity, "delayed-entry Surv(entry, exit, event)")
}
if (is_detected("informative_censoring")) {
  sensitivity <- c(sensitivity, "IPCW / sensitivity analysis; note in manuscript limitations")
}
if (is_detected("clustering")) {
  rec <- checks$clustering$recommendation
  sensitivity <- c(sensitivity,
                   if (rec == "frailty") "frailty Cox (coxme)" else "cluster-robust SE (+ cluster(id))")
}

report <- list(
  generated_at = format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z"),
  config = cfg,
  thresholds = thresh,
  checks = checks,
  recommended_primary = primary,
  recommended_secondary = as.list(unique(secondary)),
  recommended_sensitivity = as.list(unique(sensitivity))
)

json_path <- file.path(out_dir, "diagnostic_report.json")
write_json(report, json_path, auto_unbox = TRUE, pretty = TRUE, null = "null")

# ---------- Markdown summary ----------
md <- character(0); add <- function(...) md <<- c(md, paste0(...))
add("# Survival Diagnostics Report")
add("")
add("**Generated:** ", report$generated_at)
add("**Data:** `", cfg$data_file, "`  ")
add("**Output:** `", out_dir, "`")
add("")
add("## Summary")
add("")
add("| Check | Detected | Key Finding |")
add("|-------|----------|-------------|")

fmt <- function(x) if (is.null(x) || (length(x) == 1 && is.na(x))) "—" else as.character(x)
mark <- function(nm, chk) {
  if (is_detected(nm)) "✓" else if (isTRUE(chk$skipped)) "skip" else "✗"
}
cr <- checks$competing_risks
add("| Competing Risks | ", mark("competing_risks", cr),
    " | ", cr$n_event_types, " event types; divergence=", fmt(cr$cif_km_divergence), " |")
re <- checks$recurrent_events
add("| Recurrent Events | ", mark("recurrent_events", re),
    " | ", fmt(re$pct_recurrent), " of subjects; max=", fmt(re$max_events_per_subject), " |")
tv <- checks$time_varying
add("| Time-Varying Exposure | ", mark("time_varying", tv),
    " | immortal ratio=", fmt(tv$immortal_time_ratio), "; switchers=", fmt(tv$pct_switchers), "; risk=", fmt(tv$immortal_time_risk), " |")
lt <- checks$left_truncation
add("| Left Truncation | ", mark("left_truncation", lt),
    " | pct=", fmt(lt$pct_truncated), "; median entry=", fmt(lt$median_entry_time), " |")
ic <- checks$informative_censoring
add("| Informative Censoring | ", mark("informative_censoring", ic),
    " | censor rate=", fmt(ic$censoring_rate), "; min p=", fmt(ic$min_p_value), " |")
cl <- checks$clustering
add("| Clustering | ", mark("clustering", cl),
    " | var=", fmt(cl$cluster_variable), "; n=", fmt(cl$n_clusters), "; ICC=", fmt(cl$icc), " |")
add("")

add("## Recommended Routing")
add("")
add("- **Primary:** ", primary)
if (length(secondary) > 0) {
  add("- **Secondary:**")
  for (s in secondary) add("  - ", s)
}
if (length(sensitivity) > 0) {
  add("- **Sensitivity:**")
  for (s in sensitivity) add("  - ", s)
}
add("")

add("## Decision Flowchart")
add("")
add("```")
add("Start")
add("  |-- Competing risks? ", if (is_detected("competing_risks")) "YES -> /competing-risk" else "NO")
add("  |-- Recurrent events? ", if (is_detected("recurrent_events")) "YES -> out of scope" else "NO")
add("  |-- Time-varying exposure? ", if (is_detected("time_varying")) paste0("YES (risk=", checks$time_varying$immortal_time_risk, ") -> extended Cox") else "NO")
add("  |-- Left truncation? ", if (is_detected("left_truncation")) "YES -> delayed-entry Surv()" else "NO")
add("  |-- Informative censoring? ", if (is_detected("informative_censoring")) "YES -> IPCW / sensitivity" else "NO")
add("  |-- Clustering? ", if (is_detected("clustering")) paste0("YES -> ", checks$clustering$recommendation) else "NO")
add("  +-- PRIMARY: ", primary)
add("```")

md_path <- file.path(out_dir, "diagnostic_report.md")
writeLines(md, md_path)

cat("\nDiagnostic report written:\n")
cat("  ", json_path, "\n")
cat("  ", md_path, "\n")
cat("\nPrimary recommendation: ", primary, "\n")
