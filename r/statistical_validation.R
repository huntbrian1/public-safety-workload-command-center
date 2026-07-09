args <- commandArgs(trailingOnly = FALSE)
timestamp <- format(Sys.time(), "%Y-%m-%d %H:%M:%S %Z")
root <- normalizePath(getwd(), mustWork = FALSE)

zone_hour_path <- file.path(root, "data", "processed", "zone_hour_features.csv")
cluster_path_hex <- file.path(root, "outputs", "hex", "hex_cluster_profiles.csv")
cluster_path_tableau <- file.path(root, "outputs", "tableau", "tableau_cluster_profiles.csv")
out_path <- file.path(root, "outputs", "memo", "r_validation_results.txt")

read_table <- function(path) {
  if (requireNamespace("data.table", quietly = TRUE)) {
    return(as.data.frame(data.table::fread(path, showProgress = FALSE)))
  }
  read.csv(path, stringsAsFactors = FALSE)
}

lines <- c(
  "Public Safety Service Demand Intelligence - R Validation",
  "",
  paste("Timestamp:", timestamp),
  paste("R version:", R.version.string),
  paste("Working directory:", root),
  ""
)

if (!file.exists(zone_hour_path)) {
  lines <- c(lines, paste("FAIL: missing zone-hour file:", zone_hour_path))
  writeLines(lines, out_path)
  quit(save = "no", status = 1)
}

cluster_path <- if (file.exists(cluster_path_hex)) cluster_path_hex else cluster_path_tableau
if (!file.exists(cluster_path)) {
  lines <- c(lines, paste("FAIL: missing cluster profile file:", cluster_path_hex, "or", cluster_path_tableau))
  writeLines(lines, out_path)
  quit(save = "no", status = 1)
}

zone_hour <- read_table(zone_hour_path)
clusters <- read_table(cluster_path)

lines <- c(lines, paste("Zone-hour input rows:", nrow(zone_hour)))
lines <- c(lines, paste("Cluster profile rows:", nrow(clusters)))

required <- c("target_demand_count", "is_weekend", "is_after_hours", "temperature_2m", "precipitation", "zone_id")
missing <- setdiff(required, names(zone_hour))
if (length(missing) > 0) {
  lines <- c(lines, paste("FAIL: missing required zone-hour columns:", paste(missing, collapse = ", ")))
  writeLines(lines, out_path)
  quit(save = "no", status = 1)
}

zone_hour$target_demand_count <- as.numeric(zone_hour$target_demand_count)
zone_hour$is_weekend <- as.logical(zone_hour$is_weekend)
zone_hour$is_after_hours <- as.logical(zone_hour$is_after_hours)
zone_hour$temperature_2m <- as.numeric(zone_hour$temperature_2m)
zone_hour$precipitation <- as.numeric(zone_hour$precipitation)
zone_hour$month <- as.numeric(zone_hour$month)
zone_hour$hour <- as.numeric(zone_hour$hour)

set.seed(42)
analysis_sample_n <- min(nrow(zone_hour), 500000)
analysis_sample <- if (nrow(zone_hour) > analysis_sample_n) {
  zone_hour[sample.int(nrow(zone_hour), analysis_sample_n), ]
} else {
  zone_hour
}
lines <- c(lines, paste("Rows used for heavy statistical tests:", nrow(analysis_sample)))
if (nrow(zone_hour) > analysis_sample_n) {
  lines <- c(lines, "Sampling note: full row counts are reported; Wilcoxon/Kruskal/regression tests use a reproducible 500,000-row sample for practical runtime on a full-scale feature table.")
}

lines <- c(lines, "", "Weekday vs weekend demand test")
weekend_test <- wilcox.test(target_demand_count ~ is_weekend, data = analysis_sample)
weekday_mean <- mean(analysis_sample$target_demand_count[analysis_sample$is_weekend == FALSE], na.rm = TRUE)
weekend_mean <- mean(analysis_sample$target_demand_count[analysis_sample$is_weekend == TRUE], na.rm = TRUE)
lines <- c(lines, capture.output(print(weekend_test)))
lines <- c(lines, paste("Weekday mean demand:", round(weekday_mean, 4)))
lines <- c(lines, paste("Weekend mean demand:", round(weekend_mean, 4)))
lines <- c(lines, paste("Simple mean difference:", round(weekend_mean - weekday_mean, 4)))

if (!("cluster_name" %in% names(clusters))) {
  lines <- c(lines, "", "Cluster test skipped: cluster_name column not available.")
} else {
  merged <- merge(analysis_sample, clusters[, c("zone_id", "cluster_name")], by = "zone_id", all.x = TRUE)
  merged <- merged[!is.na(merged$cluster_name), ]
  lines <- c(lines, "", "Demand differences across clusters")
  if (length(unique(merged$cluster_name)) > 1) {
    kw <- kruskal.test(target_demand_count ~ cluster_name, data = merged)
    lines <- c(lines, capture.output(print(kw)))
    cluster_stats <- aggregate(target_demand_count ~ cluster_name, merged, function(x) {
      c(mean = mean(x, na.rm = TRUE), n = length(x), sd = sd(x, na.rm = TRUE))
    })
    lines <- c(lines, "", "Cluster confidence intervals around average demand")
    for (i in seq_len(nrow(cluster_stats))) {
      vals <- cluster_stats$target_demand_count[i, ]
      mean_v <- vals["mean"]
      n_v <- vals["n"]
      sd_v <- vals["sd"]
      se <- ifelse(n_v > 0, sd_v / sqrt(n_v), NA)
      ci_low <- mean_v - 1.96 * se
      ci_high <- mean_v + 1.96 * se
      lines <- c(lines, paste(cluster_stats$cluster_name[i], "mean=", round(mean_v, 4), "95% CI=[", round(ci_low, 4), ",", round(ci_high, 4), "]", "n=", n_v))
    }
  } else {
    lines <- c(lines, "Cluster test skipped: only one cluster present in merged data.")
  }
}

lines <- c(lines, "", "Regression of demand on weather/calendar features")
reg_data <- analysis_sample[, c("target_demand_count", "temperature_2m", "precipitation", "is_weekend", "is_after_hours", "month", "hour")]
reg_data <- reg_data[complete.cases(reg_data), ]
if (nrow(reg_data) > 1000) {
  model <- lm(target_demand_count ~ temperature_2m + precipitation + is_weekend + is_after_hours + month + hour, data = reg_data)
  lines <- c(lines, capture.output(summary(model)))
} else {
  lines <- c(lines, "Regression skipped: insufficient complete weather/calendar rows.")
}

lines <- c(lines, "", "Interpretation")
lines <- c(lines, "These tests validate aggregate workload-pattern differences across time, weather, and operational demand profiles. With large public metadata, small effects can become statistically significant, so practical effect size and operational usefulness matter more than p-values alone.")
lines <- c(lines, "", "Status: REAL_R_VALIDATION_RUN_COMPLETED")

writeLines(lines, out_path)
