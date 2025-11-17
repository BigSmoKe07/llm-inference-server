output "scale_out_alarm_arn" {
  value = aws_cloudwatch_metric_alarm.queue_depth_high.arn
}
