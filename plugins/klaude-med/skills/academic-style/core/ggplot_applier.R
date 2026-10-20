# ggplot_applier.R — academic-style for R users
#
# Source this file from any R analysis script:
#   source("path/to/academic-style/core/ggplot_applier.R")
#   library(ggplot2)
#   ggplot(...) + theme_journal("nature") +
#     scale_color_manual(values = palette_journal("nature"))
#
# Requires: yaml, jsonlite, ggplot2. Optional: systemfonts, showtext for font
# installation.

suppressPackageStartupMessages({
  if (!requireNamespace("yaml", quietly = TRUE)) {
    stop("R package 'yaml' required. install.packages('yaml').")
  }
  if (!requireNamespace("jsonlite", quietly = TRUE)) {
    stop("R package 'jsonlite' required. install.packages('jsonlite').")
  }
})

# Resolve the skill directory: ACADEMIC_STYLE_DIR env var, else the folder
# above this file (captured at source() time).
.academic_style_root <- local({
  env <- Sys.getenv("ACADEMIC_STYLE_DIR")
  if (nzchar(env)) {
    env
  } else {
    f <- tryCatch(sys.frame(1)$ofile, error = function(e) NULL)
    if (!is.null(f)) dirname(dirname(normalizePath(f))) else ""
  }
})
.academic_style_dir <- function() {
  if (nzchar(.academic_style_root)) .academic_style_root else
    stop("Set ACADEMIC_STYLE_DIR to the academic-style folder, or source() this file by path.")
}

.academic_style_load_spec <- function(journal) {
  base <- file.path(.academic_style_dir(), "journals", journal)
  if (!dir.exists(base)) {
    stop(sprintf("Unknown journal '%s'. Looked under %s", journal, base))
  }
  spec_path <- file.path(base, "spec.yaml")
  pal_path  <- file.path(base, "palette.json")
  if (!file.exists(spec_path)) stop(sprintf("%s missing", spec_path))
  if (!file.exists(pal_path))  stop(sprintf("%s missing", pal_path))

  spec <- yaml::read_yaml(spec_path)
  palette_data <- jsonlite::fromJSON(pal_path)
  # Drop _comment-style metadata
  palette_data <- palette_data[!startsWith(names(palette_data), "_")]
  spec$palette <- palette_data
  spec$.journal_dir <- base
  spec
}

.find_first_font <- function(stack) {
  available <- if (requireNamespace("systemfonts", quietly = TRUE)) {
    systemfonts::system_fonts()$family
  } else {
    character(0)
  }
  for (name in stack) {
    if (name %in% available) return(name)
  }
  warning(sprintf(
    "None of [%s] are installed locally; falling back to default sans family.",
    paste(stack, collapse = ", ")
  ), call. = FALSE)
  "sans"
}

#' Apply a journal theme to a ggplot object.
#'
#' @param journal Short name: "nature", "jama", "nejm", "lancet" (or any
#'   journal sub-folder under journals/).
#' @return A ggplot2 theme object.
#' @export
theme_journal <- function(journal) {
  if (!requireNamespace("ggplot2", quietly = TRUE)) {
    stop("R package 'ggplot2' required.")
  }
  spec <- .academic_style_load_spec(journal)
  typo <- spec$typography
  lines <- spec$lines
  ax    <- spec$ax_style

  font <- .find_first_font(typo$font_stack)
  sizes <- typo$sizes_pt

  spines <- ax$spines_visible %||% c("bottom", "left")
  axis_line <- ggplot2::element_line(linewidth = lines$axis_linewidth)
  no_line <- ggplot2::element_blank()

  thm <- ggplot2::theme_classic(base_family = font, base_size = typo$base_size_pt) +
    ggplot2::theme(
      plot.title       = ggplot2::element_text(size = sizes$title),
      axis.title       = ggplot2::element_text(size = sizes$axis_label),
      axis.text        = ggplot2::element_text(size = sizes$tick),
      legend.text      = ggplot2::element_text(size = sizes$legend),
      legend.title     = ggplot2::element_text(size = sizes$legend),
      axis.line.x      = if ("bottom" %in% spines) axis_line else no_line,
      axis.line.y      = if ("left"   %in% spines) axis_line else no_line,
      axis.line.x.top  = if ("top"    %in% spines) axis_line else no_line,
      axis.line.y.right= if ("right"  %in% spines) axis_line else no_line,
      axis.ticks       = ggplot2::element_line(linewidth = lines$axis_linewidth),
      axis.ticks.length = ggplot2::unit(lines$tick_length, "pt"),
      panel.grid       = if (isTRUE(ax$grid)) ggplot2::element_line(linewidth = 0.25)
                          else ggplot2::element_blank(),
      legend.background = if (isTRUE(ax$legend_frame))
                            ggplot2::element_rect(fill = "white", color = "black", linewidth = 0.3)
                          else ggplot2::element_blank()
    )
  thm
}

#' Get a hex color for a semantic role or named palette entry.
#'
#' @param journal Short name.
#' @param role Either a key from spec$semantic_mapping (e.g. "primary_method")
#'   or a direct palette name (e.g. "blue_main").
#' @return A character hex string.
#' @export
palette_journal <- function(journal, role = NULL) {
  spec <- .academic_style_load_spec(journal)
  pal  <- spec$palette
  sem  <- spec$semantic_mapping
  if (is.null(role)) {
    # Return a color cycle suitable for scale_color_manual / scale_fill_manual
    order <- c("primary_method", "control_or_negative", "positive_outcome",
               "highlight", "neutral_reference")
    out <- character(0)
    for (r in order) {
      nm <- sem[[r]]
      if (!is.null(nm) && nm %in% names(pal)) out <- c(out, pal[[nm]])
    }
    extras <- pal[!(names(pal) %in% c("black", "white") |
                    pal %in% out)]
    return(unname(c(out, unlist(extras))))
  }
  if (!is.null(sem[[role]])) return(unname(pal[[sem[[role]]]]))
  if (!is.null(pal[[role]])) return(unname(pal[[role]]))
  stop(sprintf(
    "%s: '%s' is neither a semantic role (%s) nor a palette name (%s)",
    journal, role,
    paste(names(sem), collapse = ", "),
    paste(names(pal), collapse = ", ")
  ))
}

#' Convenience: dimensions in inches for ggsave().
#'
#' @param journal Short name.
#' @param column "single", "double", or "full".
#' @return Named numeric vector with width/height in inches.
#' @export
figure_size_journal <- function(journal, column = "single") {
  spec <- .academic_style_load_spec(journal)
  dim  <- spec$dimensions
  key_map <- list(single = "single_column", double = "double_column", full = "full_width")
  key <- key_map[[column]] %||% column
  box <- dim[[key]]
  if (is.null(box)) stop(sprintf("Unknown column '%s'", column))
  width_mm <- box$width
  max_h_mm <- if (!is.null(box$max_height)) box$max_height else width_mm
  height_mm <- min(width_mm * 0.62, max_h_mm)
  c(width = width_mm / 25.4, height = height_mm / 25.4)
}

# null-coalescing helper (R 4.1+ has |> and \(), but no native ||)
`%||%` <- function(a, b) if (!is.null(a)) a else b
