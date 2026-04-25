# Portainer Deployment Guide

This guide explains how to connect this repository to Portainer and deploy updates automatically.

## 1) Deploy Stack in Portainer via Repository (Git)

1. Open Portainer and go to **Stacks**.
2. Click **Add stack**.
3. Enter a stack name (for example: `gmweb`).
4. Under **Build method**, choose **Repository**.
5. Set:
   - **Repository URL**: your GitHub repository URL
   - **Repository reference**: the branch you deploy from (for example `release`)
   - **Compose path**: `portainer-stack.yml`
6. In the **Environment variables** section, define values required by `.env` (or mount an env file on the host and reference it according to your Portainer setup).
7. Click **Deploy the stack**.

## 2) Enable Automatic updates using Webhook

1. Open the deployed stack in Portainer.
2. Click **Auto update** (or **Automatic updates**, depending on Portainer version).
3. Enable automatic updates.
4. Select **Webhook** as the update mechanism.
5. Save settings.

## 3) Add Portainer Webhook URL to GitHub Actions Secret

1. In Portainer stack settings, copy the generated **Webhook URL**.
2. In GitHub, open your repository.
3. Navigate to:
   - **Settings** -> **Secrets and variables** -> **Actions**
4. Click **New repository secret**.
5. Create:
   - **Name**: `PORTAINER_WEBHOOK_URL`
   - **Secret**: paste the copied Portainer webhook URL
6. Save the secret.

With this setup, every push/merge to the `release` branch triggers the GitHub Actions workflow, publishes a new GHCR image, and calls the Portainer webhook to redeploy automatically.
