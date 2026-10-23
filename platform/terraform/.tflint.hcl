# tflint settings for every Terraform folder here. CI runs tflint 0.59.1 with these.
# The recommended rules find unused variables, locals and lookups, missing version settings,
# and deprecated syntax. The AWS rule set is not used: it needs the plugin downloaded at run
# time, and the module tests already check the AWS settings that matter.
plugin "terraform" {
  enabled = true
  preset  = "recommended"
}
