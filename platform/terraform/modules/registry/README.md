# registry module

I use this module to create the repository that holds the Airflow image for one environment. The session box pulls the image from here.

What it does:

- **Scans every image** when it is pushed.
- **Never lets a tag be overwritten.** A version tag always means the same image. A new build gets a new tag.
- **Encrypts images** at rest.
- **Cleans up old images.** Untagged images expire after 7 days, and only the newest 10 images are kept, so storage does not grow without limit.
- **Dev can be removed with its images,** so teardown stays cheap. A live repository must be emptied by hand first.

## Inputs

| Name | Type | Default | Description |
|---|---|---|---|
| `env` | string | none | `dev` or `live`. |

## Outputs

| Name | Description |
|---|---|
| `repository_url` | Address of the repository. The install script takes it as `IMAGE_REPOSITORY`. |
| `repository_arn` | ARN of the repository. The `box_iam` module uses it. |
