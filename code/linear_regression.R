# Linear Regression Analysis
# Read the data

dat <- read.csv("mydata.csv")

# Fit the model
model <- lm(y ~ x, data = dat)

# Display the results
summary(model)
