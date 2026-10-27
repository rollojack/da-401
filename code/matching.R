# Matched-pair selection: Derby participants vs. non-participating All-Stars
#
# Pairs each Derby participant with the closest non-participating All-Star
# from the same season, by Mahalanobis distance on standardized FIRST-HALF
# batted-ball variables (Stuart, 2010). Uses first-half data only, so the
# matching cannot be influenced by second-half outcomes.
#
# Inputs (all in data/):
#   Statcast_Participants_H1.csv  - first-half metrics, participants
#   Statcast_Pool_H1.csv          - first-half metrics, All-Star candidates
#   Control_Pool.csv              - candidates' PA in each half
#   Savant_Batted_Ball.csv        - participants' PA in each half
# (the Statcast_* files come from code/pull_statcast_halves.py and the pool
#  from code/build_control_pool.py)
#
# Outputs (all in data/):
#   Matched_Pairs.csv             - one row per matched participant-control pair
#   Unmatched_Participants.csv    - participants with no candidate inside the caliper
#                                   (these go to the within-subject backup design)
#   Matching_Balance.csv          - standardized mean differences before/after matching
#   Matching_Reference_Stats.csv  - first-half means/SDs used for the z-scores;
#                                   reuse these to standardize second-half values
#
# Run from the repo root:  Rscript code/matching.R

# ---- Pre-registered settings (fix these BEFORE looking at any 2nd-half data) ----

# Minimum plate appearances required in EACH half to be eligible
MIN_PA <- 150

# Matching variables (first half)
VARS <- c("pull_pct", "fb_pct", "k_pct", "hr_fb", "avg_ev", "avg_la")

# Maximum allowed Mahalanobis distance for a pair (the caliper).
# If two hitters were drawn at random from the same population, their squared
# Mahalanobis distance follows 2 * chi-square(p). This caliper accepts a pair
# only if it is closer than 90% of random pairs would be.
CALIPER_PERCENTILE <- 0.10
CALIPER <- sqrt(2 * qchisq(CALIPER_PERCENTILE, df = length(VARS)))

# ---- Load and combine ----

read_h1 <- function(path) {
  d <- read.csv(path, check.names = FALSE)
  data.frame(
    player   = d$Player,
    mlbam_id = d$`MLBAM ID`,
    season   = d$Season,
    pa_h1    = d$PA,
    pull_pct = d$`Pull%`,
    fb_pct   = d$`FB%`,
    k_pct    = d$`K%`,
    hr_fb    = d$`HR/FB`,
    avg_ev   = d$`Avg EV`,
    avg_la   = d$`Avg LA`
  )
}

parts <- read_h1("data/Statcast_Participants_H1.csv")
parts$derby <- 1
savant <- read.csv("data/Savant_Batted_Ball.csv", check.names = FALSE)
h2 <- savant[savant$Half == "2nd", c("MLBAM ID", "Season", "PA")]
names(h2) <- c("mlbam_id", "season", "pa_h2")
parts <- merge(parts, h2, by = c("mlbam_id", "season"), all.x = TRUE)

pool <- read_h1("data/Statcast_Pool_H1.csv")
pool$derby <- 0
pool_pa <- read.csv("data/Control_Pool.csv", check.names = FALSE)
pool_pa <- data.frame(mlbam_id = pool_pa$`MLBAM ID`, season = pool_pa$Season,
                      pa_h2 = pool_pa$`2nd PA`)
pool <- merge(pool, pool_pa, by = c("mlbam_id", "season"), all.x = TRUE)

all <- rbind(parts, pool)

# ---- Eligibility ----

all$eligible <- with(all, pa_h1 >= MIN_PA & pa_h2 >= MIN_PA &
                       complete.cases(all[, VARS]))
cat("Ineligible (PA <", MIN_PA, "in a half, or missing data):\n")
print(all[!all$eligible, c("season", "player", "derby", "pa_h1", "pa_h2")],
      row.names = FALSE)
elig <- all[all$eligible, ]

# ---- Standardize with the eligible first-half sample ----

ref <- data.frame(variable = VARS,
                  mean = sapply(elig[, VARS], mean),
                  sd   = sapply(elig[, VARS], sd))
z <- scale(elig[, VARS], center = ref$mean, scale = ref$sd)
S_inv <- solve(cov(z))

# ---- Greedy nearest-neighbor matching within season, closest pairs first ----

pairs <- list()
for (s in sort(unique(elig$season))) {
  t_idx <- which(elig$season == s & elig$derby == 1)
  c_idx <- which(elig$season == s & elig$derby == 0)
  if (length(t_idx) == 0 || length(c_idx) == 0) next

  # distance matrix: rows = participants, cols = candidates
  D <- sapply(c_idx, function(j)
    sapply(t_idx, function(i) {
      diff <- z[i, ] - z[j, ]
      sqrt(drop(t(diff) %*% S_inv %*% diff))
    }))
  D <- matrix(D, nrow = length(t_idx))

  while (any(is.finite(D))) {
    k <- which(D == min(D), arr.ind = TRUE)[1, ]
    i <- t_idx[k[1]]; j <- c_idx[k[2]]
    pairs[[length(pairs) + 1]] <- data.frame(
      season = s,
      participant = elig$player[i], participant_id = elig$mlbam_id[i],
      control = elig$player[j], control_id = elig$mlbam_id[j],
      distance = round(D[k[1], k[2]], 3))
    D[k[1], ] <- Inf
    D[, k[2]] <- Inf
  }
}
pairs <- do.call(rbind, pairs)

matched <- pairs[pairs$distance <= CALIPER, ]
key <- paste(elig$mlbam_id, elig$season)
unmatched <- elig[elig$derby == 1 &
                    !(key %in% paste(matched$participant_id, matched$season)),
                  c("season", "player", "mlbam_id")]
nearest <- pairs[, c("season", "participant_id", "control", "distance")]
names(nearest) <- c("season", "mlbam_id", "closest_candidate", "closest_distance")
unmatched <- merge(unmatched, nearest, by = c("season", "mlbam_id"), all.x = TRUE)

# ---- Balance: standardized mean differences ----

smd <- function(t, c) (mean(t) - mean(c)) / sqrt((var(t) + var(c)) / 2)
zt <- z[elig$derby == 1, , drop = FALSE]
zc <- z[elig$derby == 0, , drop = FALSE]
zt_m <- z[key %in% paste(matched$participant_id, matched$season) & elig$derby == 1, , drop = FALSE]
zc_m <- z[key %in% paste(matched$control_id, matched$season) & elig$derby == 0, , drop = FALSE]
balance <- data.frame(
  variable = VARS,
  smd_before = round(sapply(VARS, function(v) smd(zt[, v], zc[, v])), 3),
  smd_after  = round(sapply(VARS, function(v) smd(zt_m[, v], zc_m[, v])), 3))

# ---- Report and save ----

cat("\nCaliper (max Mahalanobis distance):", round(CALIPER, 3), "\n")
cat("Eligible participants:", sum(elig$derby == 1),
    " | eligible candidates:", sum(elig$derby == 0), "\n")
cat("Matched pairs:", nrow(matched),
    " | unmatched participants (-> within-subject backup):", nrow(unmatched), "\n")
cat("\nPair distances (all greedy pairs, before caliper):\n")
print(summary(pairs$distance))
cat("\nBalance (|SMD| < 0.1 is good, < 0.25 acceptable):\n")
print(balance, row.names = FALSE)

write.csv(matched, "data/Matched_Pairs.csv", row.names = FALSE)
write.csv(unmatched, "data/Unmatched_Participants.csv", row.names = FALSE)
write.csv(balance, "data/Matching_Balance.csv", row.names = FALSE)
write.csv(ref, "data/Matching_Reference_Stats.csv", row.names = FALSE)
