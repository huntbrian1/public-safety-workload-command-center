# AWS Deployment Notes

The core project runs locally without AWS. Use AWS only when you want to publish outputs or host the Streamlit app.

## Upload Outputs to S3

1. Install `boto3`.
2. Configure AWS credentials outside this repo.
3. Set `S3_BUCKET` and optionally `S3_PREFIX`.
4. Run `python deploy/aws/s3_upload.py`.

## Streamlit Hosting Options

- Build and push the Docker image to ECR, then adapt `ecs_task_definition.example.json` for ECS Fargate.
- For a simpler demo, run the app on EC2 and mount generated `outputs/` and `data/processed/`.

No credentials or secrets are stored in this repository.
