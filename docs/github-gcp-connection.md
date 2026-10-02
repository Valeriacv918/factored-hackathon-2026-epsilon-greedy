# GitHub to Google Cloud

The `Sync Dataform` GitHub Actions workflow validates Dataform source on pushes
to `main`, writes it to the existing `bank-transformations/development`
workspace, and requests a compilation. Compilation does not execute SQL or
publish BigQuery tables. A separate, reviewed invocation is still required.

Authentication uses GitHub OIDC and Google Workload Identity Federation. Do not
create or store a service-account key. A Google Cloud project administrator
must run the one-time setup below in Cloud Shell. Confirm the GitHub repository
owner and name from `git remote -v` first; update `GITHUB_REPOSITORY` and the
provider condition if this checkout is a fork. The workflow assumes the deploy
branch is `main`.

```bash
export PROJECT_ID="hackaton-509923"
export GITHUB_REPOSITORY="Valeriacv918/factored-hackathon-2026-epsilon-greedy"
export POOL_ID="github-actions"
export PROVIDER_ID="github"
export DEPLOYER="dataform-github-deployer"
export REGION="us-central1"
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
export DEPLOYER_EMAIL="${DEPLOYER}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud services enable iamcredentials.googleapis.com sts.googleapis.com \
  dataform.googleapis.com --project="$PROJECT_ID"

gcloud iam workload-identity-pools create "$POOL_ID" \
  --project="$PROJECT_ID" --location=global \
  --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
  --project="$PROJECT_ID" --location=global \
  --workload-identity-pool="$POOL_ID" \
  --display-name="GitHub repository main branch" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository == '${GITHUB_REPOSITORY}' && assertion.ref == 'refs/heads/main'"

gcloud iam service-accounts create "$DEPLOYER" --project="$PROJECT_ID" \
  --display-name="GitHub Dataform deployer"

gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER_EMAIL" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.repository/${GITHUB_REPOSITORY}"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOYER_EMAIL}" \
  --role="roles/dataform.editor"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOYER_EMAIL}" \
  --role="roles/serviceusage.serviceUsageConsumer"
```

If the pool, provider, or service account already exists, inspect it and skip
its `create` command. Do not replace an existing provider or broaden its
attribute condition without reviewing its trust boundary. The deployer identity
is separate from `bank-curation`; it can edit and compile Dataform source, but
the workflow does not use it to run compiled SQL.

In the GitHub repository, open **Settings > Secrets and variables > Actions**
and create these repository secrets:

| Secret | Value |
|---|---|
| `GCP_WIF_PROVIDER` | `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions/providers/github` |
| `GCP_DATAFORM_DEPLOYER` | `dataform-github-deployer@hackaton-509923.iam.gserviceaccount.com` |

Replace `PROJECT_NUMBER` with the numeric project number, not the project ID.
After setup, push a change under `data/dataform/` to `main`, or run **Actions >
Sync Dataform > Run workflow**. A successful `COMPILED` result confirms the
repository can authenticate, update the remote workspace, and compile through
the Dataform API. It does not certify or execute a table publication.

The existing manual uploader remains available from authenticated Cloud Shell.
The GitHub workflow serializes updates to the shared `development` workspace;
use a separate workspace if parallel development is needed.