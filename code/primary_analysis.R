# Primary and secondary analyses: Home Run Derby participation and change in
# batted-ball approach.
#
# Input:  data/Analysis_Dataset.csv  (from code/build_analysis_dataset.py)
# Output: printed results + data/Results.csv
#
# Run from the repo root:  Rscript code/primary_analysis.R
#
# Analysis plan (fixed before any second-half result was examined):
#
# PRIMARY (confirmatory, tested once, alpha = .05)
#   Outcome: change in Pull-Air Index (PAI_2nd - PAI_1st), where PAI = mean of
#   z(FanGraphs Pull%) and z(FanGraphs FB%), both halves standardized with the
#   first-half mean/SD of the full eligible sample.
#   Test: matched participants vs. their controls, linear regression of
#   PAI_change on Derby status, adjusted for first-half PAI (controls for
#   regression to the mean) and the remaining first-half matching variables
#   (K%, HR/FB, Avg EV, Avg LA), since matching left residual imbalance.
#   Reported: adjusted difference with 95% CI.
#
# SUPPORTING (descriptive, as in the research design)
#   1. Paired t-test of PAI_2nd vs PAI_1st within ALL eligible participants.
#   2. Unadjusted Welch t-test of PAI_change, matched participants vs controls.
#
# SECONDARY (exploratory, Bonferroni alpha = .05 / 2 = .025)
#   a. HR/FB change: same adjusted regression as the primary.
#   b. HR Pull% change: same adjusted regression. HR direction is classified
#      automatically from Statcast hit coordinates for both groups
#      (code/hr_spray_statcast.py; 97.8% agreement with manual coding of the
#      participants). This control comparison replaced an initial
#      participants-only paired t-test, which is still reported as supporting.
#
# EXPLORATORY
#   Regime check: one-way ANOVA of PAI_change across regime (timer/swing) x
#   status (derby/control), Tukey HSD for pairwise contrasts. The swing regime
#   (2026) has only a handful of pairs, so this is underpowered.

ALPHA_PRIMARY   <- 0.05
N_SECONDARY     <- 2
ALPHA_SECONDARY <- ALPHA_PRIMARY / N_SECONDARY

d <- read.csv("data/Analysis_Dataset.csv", check.names = FALSE)
names(d) <- gsub("[%/]", "_", names(d))   # e.g. "Pull%_1st" -> "Pull__1st"
d$derby <- as.integer(d$group == "derby")
m <- d[d$matched == 1, ]                   # 71 participants + 71 controls
parts <- d[d$group == "derby", ]           # all eligible participants

results <- list()
add <- function(analysis, estimate, lo, hi, p, n, alpha) {
  results[[length(results) + 1]] <<- data.frame(
    analysis = analysis, estimate = round(estimate, 3),
    ci_low = round(lo, 3), ci_high = round(hi, 3),
    p_value = signif(p, 3), n = n, alpha = alpha,
    significant = p < alpha)
}

adjusted_effect <- function(outcome, baseline, data, label, alpha) {
  f <- as.formula(paste(outcome, "~ derby +", baseline,
                        "+ k_pct_h1 + sc_hr_fb_h1 + avg_ev_h1 + avg_la_h1"))
  fit <- lm(f, data = data)
  ci <- confint(fit, "derby", level = 1 - alpha)
  cat("\n----", label, "----\n")
  print(summary(fit)$coefficients)
  add(label, coef(fit)["derby"], ci[1], ci[2],
      summary(fit)$coefficients["derby", "Pr(>|t|)"], nrow(model.frame(fit)), alpha)
}

# ---- PRIMARY ----
adjusted_effect("PAI_change", "PAI_1st", m,
                "PRIMARY: PAI change, derby vs control (adjusted)", ALPHA_PRIMARY)

# ---- SUPPORTING ----
pt <- t.test(parts$PAI_2nd, parts$PAI_1st, paired = TRUE)
add("Supporting: PAI change within participants (paired t)",
    pt$estimate, pt$conf.int[1], pt$conf.int[2], pt$p.value, nrow(parts), ALPHA_PRIMARY)

wt <- t.test(PAI_change ~ factor(derby, levels = c(1, 0)), data = m)
add("Supporting: PAI change, derby vs control (unadjusted Welch t)",
    wt$estimate[1] - wt$estimate[2], wt$conf.int[1], wt$conf.int[2], wt$p.value,
    nrow(m), ALPHA_PRIMARY)

# ---- SECONDARY ----
adjusted_effect("HR_FB_change", "HR_FB_1st", m,
                "Secondary: HR/FB change, derby vs control (adjusted)", ALPHA_SECONDARY)

adjusted_effect("HR_Pull__change", "HR_Pull__1st", m,
                "Secondary: HR Pull% change, derby vs control (adjusted)", ALPHA_SECONDARY)

hp <- parts[complete.cases(parts[, c("HR_Pull__1st", "HR_Pull__2nd")]), ]
ht <- t.test(hp$HR_Pull__2nd, hp$HR_Pull__1st, paired = TRUE,
             conf.level = 1 - ALPHA_SECONDARY)
add("Supporting: HR Pull% change within participants (paired t)",
    ht$estimate, ht$conf.int[1], ht$conf.int[2], ht$p.value, nrow(hp), ALPHA_SECONDARY)

# ---- EXPLORATORY: regime x status ----
m$cell <- interaction(m$regime, m$group, sep = "_")
cat("\n---- Exploratory: regime x status ----\n")
print(table(m$cell))
av <- aov(PAI_change ~ cell, data = m)
print(summary(av))
print(TukeyHSD(av))

# ---- Report ----
res <- do.call(rbind, results)
cat("\n==== SUMMARY ====\n")
print(res, row.names = FALSE)
write.csv(res, "data/Results.csv", row.names = FALSE)
