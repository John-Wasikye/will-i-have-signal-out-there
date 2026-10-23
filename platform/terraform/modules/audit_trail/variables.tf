variable "size_alarm_bytes" {
  description = "Size in bytes that raises the log bucket's size alarm. The default is 10 GB, far above a year of management events for this account."
  type        = number
  default     = 10737418240
}

variable "alarm_actions" {
  description = "ARNs notified when the size alarm fires, for example the run alerts topic. Empty means the alarm only changes state."
  type        = list(string)
  default     = []
}
