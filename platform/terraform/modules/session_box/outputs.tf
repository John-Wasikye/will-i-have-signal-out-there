output "instance_id" {
  description = "ID of the session box. Use it to start the box by hand or to read its state."
  value       = aws_instance.box.id
}

output "idle_alarm_name" {
  description = "Name of the alarm that stops the box when it is idle."
  value       = aws_cloudwatch_metric_alarm.idle.alarm_name
}
