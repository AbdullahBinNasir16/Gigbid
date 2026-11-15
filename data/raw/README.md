# Raw data (git ignored)

Kaggle downloads live here, one folder per dataset. Never commit them.

| Folder | Kaggle dataset |
|---|---|
| upwork_jobs_50k | asaniczka/upwork-job-postings-dataset-2024-50k-records |
| all_upwork_jobs_200k | asaniczka/all-jobs-on-upwork-200k-plus |
| upwork_freelance_jobs_60k | ahmedmyalo/upwork-freelance-jobs-60k |
| freelance_contracts_1_3m | asaniczka/freelance-contracts-dataset-1-3-million-entries |
| freelancer_success_churn | sarveshchhetri/freelancer-success-earnings-and-churn-prediction |
| trial_1 | adityammantri/trial-1 |
| _zips | the original zip downloads |

Rebuild: `pip install -e ".[dev,data]"`, then `python -m scripts.data.build_real_jobs` and
`python -m scripts.data.build_priors`.
