# Regression assumption checks and robustness for the adjusted models in
# code/primary_analysis.R.
#
# For each adjusted model (primary Pull-Air Index; secondary HR/FB and HR Pull%):
#   - Normality of residuals: Shapiro-Wilk test + Q-Q plot
#   - Constant variance: Breusch-Pagan test + residuals-vs-fitted plot
#   - Linearity / functional form: Ramsey RESET test
#   - Multicollinearity: variance inflation factors (VIF)
#   - Influential observations: Cook's distance (flag > 4/n), and a refit
#     without the flagged observations
#   - Robust inference: the Derby estimate with heteroskedasticity-robust (HC3)
#     standard errors and with standard errors clustered by matched pair
#
# Input:  data/Analysis_Dataset.csv
# Output: data/Model_Diagnostics.csv, data/Model_Robustness.csv,
#         figures/figA1_diagnostics.png
#
# Run from the repo root:  Rscript code/model_diagnostics.R

suppressPackageStartupMessages({
  library(lmtest); library(sandwich); library(car)
  library(ggplot2); library(patchwork)
})

d <- read.csv("data/Analysis_Dataset.csv", check.names = FALSE)
names(d) <- gsub("[%/]", "_", names(d))
d$derby <- as.integer(d$group == "derby")
m <- d[d$matched == 1, ]

COVARS <- "k_pct_h1 + sc_hr_fb_h1 + avg_ev_h1 + avg_la_h1"
models <- list(
  list(label = "Primary: Pull-Air Index", outcome = "PAI_change",
       baseline = "PAI_1st", alpha = 0.05),
  list(label = "Secondary: HR/FB", outcome = "HR_FB_change",
       baseline = "HR_FB_1st", alpha = 0.025),
  list(label = "Secondary: HR Pull%", outcome = "HR_Pull__change",
       baseline = "HR_Pull__1st", alpha = 0.025))

diag_rows <- list(); rob_rows <- list(); plots <- list()

derby_row <- function(fit, vc, label, se_type, alpha) {
  ct <- coeftest(fit, vcov. = vc)
  est <- ct["derby", "Estimate"]; se <- ct["derby", "Std. Error"]
  q <- qt(1 - alpha / 2, df = fit$df.residual)
  data.frame(model = label, se_type = se_type, estimate = round(est, 3),
             se = round(se, 3), ci_low = round(est - q * se, 3),
             ci_high = round(est + q * se, 3),
             p_value = signif(ct["derby", "Pr(>|t|)"], 3), alpha = alpha,
             significant = ct["derby", "Pr(>|t|)"] < alpha, n = nobs(fit))
}

for (mod in models) {
  f <- as.formula(paste(mod$outcome, "~ derby +", mod$baseline, "+", COVARS))
  data <- m[complete.cases(m[, all.vars(f)]), ]
  data$pair_id <- as.integer(data$pair_id)
  fit <- lm(f, data = data)
  n <- nobs(fit)
  cook <- cooks.distance(fit)
  flagged <- which(cook > 4 / n)
  vifs <- vif(fit)

  diag_rows[[length(diag_rows) + 1]] <- data.frame(
    model = mod$label, n = n,
    shapiro_W = round(shapiro.test(resid(fit))$statistic, 3),
    shapiro_p = signif(shapiro.test(resid(fit))$p.value, 3),
    breusch_pagan_p = signif(bptest(fit)$p.value, 3),
    reset_p = signif(resettest(fit, power = 2:3)$p.value, 3),
    max_vif = round(max(vifs), 2),
    max_vif_term = names(which.max(vifs)),
    max_cooks_d = round(max(cook), 3),
    n_cooks_over_4_n = length(flagged))

  rob_rows[[length(rob_rows) + 1]] <- derby_row(fit, vcov(fit), mod$label,
                                                "Classical OLS", mod$alpha)
  rob_rows[[length(rob_rows) + 1]] <- derby_row(fit, vcovHC(fit, type = "HC3"),
                                                mod$label, "HC3 robust", mod$alpha)
  rob_rows[[length(rob_rows) + 1]] <- derby_row(fit, vcovCL(fit, cluster = ~pair_id),
                                                mod$label, "Clustered by pair",
                                                mod$alpha)
  if (length(flagged) > 0) {
    refit <- lm(f, data = data[-flagged, ])
    rob_rows[[length(rob_rows) + 1]] <- derby_row(
      refit, vcov(refit), mod$label,
      sprintf("Excluding %d influential obs.", length(flagged)), mod$alpha)
  }

  # Diagnostic plots: residuals vs fitted, and normal Q-Q
  pd <- data.frame(fitted = fitted(fit), resid = resid(fit),
                   std = rstandard(fit))
  pd$theory <- qqnorm(pd$std, plot.it = FALSE)$x
  th <- theme_minimal(base_size = 9) +
    theme(plot.title = element_text(size = 9, face = "bold"),
          panel.grid.minor = element_blank())
  p_rf <- ggplot(pd, aes(fitted, resid)) +
    geom_hline(yintercept = 0, colour = "#52514e", linewidth = 0.4) +
    geom_point(colour = "#2a78d6", alpha = 0.7, size = 1.4) +
    geom_smooth(method = "loess", formula = y ~ x, se = FALSE,
                colour = "#eb6834", linewidth = 0.7) +
    labs(title = paste0(mod$label, ": residuals vs. fitted"),
         x = "Fitted value", y = "Residual") + th
  p_qq <- ggplot(pd, aes(theory, std)) +
    geom_abline(slope = 1, intercept = 0, colour = "#52514e", linewidth = 0.4) +
    geom_point(colour = "#2a78d6", alpha = 0.7, size = 1.4) +
    labs(title = paste0(mod$label, ": normal Q-Q"),
         x = "Theoretical quantile", y = "Standardized residual") + th
  plots[[length(plots) + 1]] <- p_rf
  plots[[length(plots) + 1]] <- p_qq
}

diag_tab <- do.call(rbind, diag_rows); rownames(diag_tab) <- NULL
rob_tab <- do.call(rbind, rob_rows); rownames(rob_tab) <- NULL
write.csv(diag_tab, "data/Model_Diagnostics.csv", row.names = FALSE)
write.csv(rob_tab, "data/Model_Robustness.csv", row.names = FALSE)

fig <- wrap_plots(plots, ncol = 2) + plot_annotation(
  caption = paste0("Orange line: loess smooth of residuals (flat = no systematic pattern).\n",
                   "Q-Q points near the diagonal indicate approximately normal residuals."),
  theme = theme(plot.caption = element_text(size = 8, colour = "#52514e", hjust = 0)))
ggsave("figures/figA1_diagnostics.png", fig, width = 6.5, height = 7.5,
       dpi = 300, bg = "white")

cat("\n==== Assumption checks ====\n"); print(diag_tab, row.names = FALSE)
cat("\n==== Derby estimate under alternative standard errors ====\n")
print(rob_tab, row.names = FALSE)

# Normality of the paired differences behind the supporting paired t-test
parts <- d[d$group == "derby", ]
cat("\nShapiro-Wilk on participants' PAI change (paired t-test): p =",
    signif(shapiro.test(parts$PAI_change)$p.value, 3), "\n")
