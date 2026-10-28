# Figures for the early-results paper.
#
# Inputs (data/): Matching_Balance.csv, Analysis_Dataset.csv, Results.csv
# Outputs (figures/): fig1_balance.png, fig2_pai_by_half.png,
#                     fig3_effects.png, fig4_hr_pull_by_half.png
#
# Run from the repo root:  Rscript code/figures.R

library(ggplot2)
library(patchwork)

DERBY   <- "#2a78d6"   # categorical slot 1
CONTROL <- "#eb6834"   # categorical slot 2
BEFORE  <- "#9a9993"   # neutral gray for "before matching"
INK     <- "#0b0b0b"
INK2    <- "#52514e"
GRID    <- "#e6e5e1"

theme_paper <- function() {
  theme_minimal(base_size = 11) +
    theme(text = element_text(colour = INK),
          axis.text = element_text(colour = INK2),
          axis.title = element_text(colour = INK2),
          panel.grid.major = element_line(colour = GRID, linewidth = 0.4),
          panel.grid.minor = element_blank(),
          plot.title = element_text(face = "bold", size = 12),
          plot.subtitle = element_text(colour = INK2, size = 10),
          plot.caption = element_text(colour = INK2, size = 8, hjust = 0),
          plot.title.position = "plot", plot.caption.position = "plot",
          legend.position = "top", legend.justification = "left",
          legend.title = element_blank(),
          plot.background = element_rect(fill = "white", colour = NA))
}
wrap <- function(x, width = 115) paste(strwrap(x, width), collapse = "
")
save <- function(p, file, h) ggsave(file.path("figures", file), p, width = 6.5,
                                    height = h, dpi = 300, bg = "white")

d <- read.csv("data/Analysis_Dataset.csv", check.names = FALSE)
m <- d[d$matched == 1, ]
m$Group <- factor(ifelse(m$group == "derby", "Derby participants", "Matched controls"),
                  levels = c("Derby participants", "Matched controls"))
group_cols <- c("Derby participants" = DERBY, "Matched controls" = CONTROL)

# ---- Figure 1: covariate balance before and after matching ----
bal <- read.csv("data/Matching_Balance.csv")
labels <- c(pull_pct = "Pull%", fb_pct = "FB%", k_pct = "K%", hr_fb = "HR/FB",
            avg_ev = "Avg exit velocity", avg_la = "Avg launch angle")
bal$Variable <- factor(labels[bal$variable], levels = labels[bal$variable[order(bal$smd_before)]])
bal_long <- rbind(
  data.frame(Variable = bal$Variable, smd = abs(bal$smd_before), When = "Before matching"),
  data.frame(Variable = bal$Variable, smd = abs(bal$smd_after),  When = "After matching"))
bal_long$When <- factor(bal_long$When, levels = c("Before matching", "After matching"))

p1 <- ggplot(bal_long, aes(smd, Variable)) +
  annotate("rect", xmin = -Inf, xmax = 0.25, ymin = -Inf, ymax = Inf,
           fill = "#f3f2ee") +
  geom_vline(xintercept = c(0.1, 0.25), colour = INK2, linetype = "dashed", linewidth = 0.4) +
  geom_line(aes(group = Variable), colour = GRID, linewidth = 1) +
  geom_point(aes(colour = When, shape = When), size = 3, stroke = 1.2) +
  scale_colour_manual(values = c("Before matching" = BEFORE, "After matching" = DERBY)) +
  scale_shape_manual(values = c("Before matching" = 1, "After matching" = 16)) +
  scale_x_continuous(limits = c(0, 0.8), breaks = seq(0, 0.8, 0.1), expand = expansion(add = c(0, 0.02))) +
  labs(title = "Matching shrank the largest first-half differences",
       subtitle = "Absolute standardized mean difference, Derby participants vs. All-Star candidates",
       x = "|Standardized mean difference|", y = NULL,
       caption = wrap("Dashed lines mark 0.10 (good) and 0.25 (acceptable). Before: 85 participants vs. 342 candidates; after: 71 matched pairs.")) +
  theme_paper()
save(p1, "fig1_balance.png", 3.6)

# ---- Helper: group means by half with 95% CIs ----
by_half <- function(var1, var2) {
  out <- do.call(rbind, lapply(levels(m$Group), function(g) {
    do.call(rbind, lapply(c("First half", "Second half"), function(h) {
      x <- m[m$Group == g, if (h == "First half") var1 else var2]
      x <- x[!is.na(x)]
      se <- sd(x) / sqrt(length(x))
      data.frame(Group = g, Half = h, mean = mean(x),
                 lo = mean(x) - qt(.975, length(x) - 1) * se,
                 hi = mean(x) + qt(.975, length(x) - 1) * se)
    }))
  }))
  out$Group <- factor(out$Group, levels = levels(m$Group))
  out
}

half_plot <- function(s, title, subtitle, ylab, caption, fmt) {
  dodge <- position_dodge(width = 0.12)
  ends <- s[s$Half == "Second half", ]
  ggplot(s, aes(Half, mean, colour = Group, group = Group)) +
    geom_line(linewidth = 1, position = dodge) +
    geom_errorbar(aes(ymin = lo, ymax = hi), width = 0.05, linewidth = 0.6, position = dodge) +
    geom_point(size = 3.2, position = dodge) +
    geom_text(data = ends, aes(label = paste0(Group, "  ", fmt(mean))),
              hjust = 0, nudge_x = 0.12, size = 3.4, colour = INK, show.legend = FALSE) +
    scale_colour_manual(values = group_cols) +
    scale_x_discrete(expand = expansion(add = c(0.3, 1.15))) +
    labs(title = title, subtitle = subtitle, x = NULL, y = ylab, caption = wrap(caption)) +
    theme_paper()
}

# ---- Figure 2: Pull-Air Index by half ----
s2 <- by_half("PAI_1st", "PAI_2nd")
p2 <- half_plot(s2,
  "Derby participants started higher and rose slightly more",
  "Mean Pull-Air Index by half, 71 matched pairs (error bars: 95% CI)",
  "Pull-Air Index (SD units)",
  "Pull-Air Index = mean of standardized FanGraphs Pull% and FB%, standardized with the first-half mean/SD of all 427 eligible hitters.",
  function(x) sprintf("%.2f", x))
save(p2, "fig2_pai_by_half.png", 3.8)

# ---- Figure 3: effect estimates ----
r <- read.csv("data/Results.csv")
r$label <- c("Adjusted, matched (primary)", "Within participants (paired)",
             "Unadjusted, matched (Welch)", "HR/FB (adjusted)",
             "HR Pull% (adjusted)", "HR Pull%, within participants (supporting)")
r$kind <- ifelse(grepl("^PRIMARY", r$analysis), "Primary",
                 ifelse(grepl("^Secondary", r$analysis), "Secondary", "Supporting"))
r$label <- paste0(r$label, "  (p = ", formatC(r$p_value, format = "f", digits = 3), ")")

forest <- function(rows, title, xlab, cap) {
  rows$label <- factor(rows$label, levels = rev(rows$label))
  ggplot(rows, aes(estimate, label)) +
    geom_vline(xintercept = 0, colour = INK2, linewidth = 0.5) +
    geom_errorbar(aes(xmin = ci_low, xmax = ci_high), orientation = "y", width = 0.15,
                  colour = DERBY, linewidth = 0.8) +
    geom_point(aes(shape = kind), colour = DERBY, size = 3.2, fill = "white", stroke = 1.2) +
    scale_shape_manual(values = c(Primary = 18, Secondary = 16, Supporting = 21),
                       breaks = c("Primary", "Secondary", "Supporting")) +
    labs(title = title, x = xlab, y = NULL, caption = if (is.null(cap)) NULL else wrap(cap)) +
    theme_paper() + theme(legend.position = "none", plot.title = element_text(size = 11))
}
p3a <- forest(r[1:3, ], "A. Pull-Air Index change (95% CI)",
              "Derby effect, SD units (positive = more pull-air)", NULL)
p3b <- forest(r[4:6, ], "B. Secondary outcomes (97.5% CI, Bonferroni)",
              "Derby effect, percentage points",
              "Estimates are the Derby-minus-control difference in first-to-second-half change, except 'within participants' (second minus first half).")
p3 <- p3a / p3b + plot_annotation(
  title = wrap("Every estimate leans toward more pull-air hitting, but no Derby-vs-control difference is significant", 80),
  theme = theme_paper())
save(p3, "fig3_effects.png", 5.4)

# ---- Figure 4: HR Pull% by half ----
s4 <- by_half("HR_Pull%_1st", "HR_Pull%_2nd")
p4 <- half_plot(s4,
  "Derby participants pulled more of their home runs after the break",
  "Mean share of home runs pulled, by half, 71 matched pairs (error bars: 95% CI)",
  "Home runs pulled (%)",
  "HR direction classified from Statcast hit coordinates (pull side beyond 15 degrees); 97.8% agreement with manual spray-chart coding.",
  function(x) sprintf("%.1f%%", x))
save(p4, "fig4_hr_pull_by_half.png", 3.8)

cat("Saved 4 figures to figures/\n")
