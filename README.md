# SeeFood Enterprise

SeeFood Enterprise classifies images as "Hot Dog" or "Not Hot Dog" for teams.
A user signs in, drops one or more images, and reads a verdict with a confidence score.
The browser uploads each image straight to object storage. A worker runs the vision
model and writes the result. Verdicts below the confidence threshold go to a review
queue, where a team member confirms or overrides them. History supports filters and
CSV export. The dashboard shows totals, hot dog ratio, latency, spend, and override rate.

Status: repository structure only. No application code yet.

## AI use

This project was built with Claude Code and Codex. They acted as conductor,
implementers, and reviewers. The human made the product and priority decisions.
