# Data notices and attribution

Files in this folder are derived from the Kaggle datasets below. Derived files were cleaned,
de-duplicated and PII masked by `scripts/data/build_real_jobs.py` and
`scripts/data/build_priors.py` (modifications: schema normalisation, HTML decoding,
removal of emails, URLs, phone numbers and messenger handles, category and skill tagging,
sampling, aggregation). Job posting text remains the work of its original posters on Upwork.
GigBid is not affiliated with Upwork or the dataset authors.

| Dataset | Author | Licence | Used in |
|---|---|---|---|
| [Upwork Job Postings Dataset 2024 (50k records)](https://www.kaggle.com/datasets/asaniczka/upwork-job-postings-dataset-2024-50k-records) | asaniczka | [ODC-By v1.0](https://opendatacommons.org/licenses/by/1-0/) | job_stream_1500.parquet, job_stream_sample.json, price_stats.json |
| [All Jobs on Upwork (200k+)](https://www.kaggle.com/datasets/asaniczka/all-jobs-on-upwork-200k-plus) | asaniczka | [ODC-By v1.0](https://opendatacommons.org/licenses/by/1-0/) | price_stats.json |
| [Upwork Freelance Jobs (60k)](https://www.kaggle.com/datasets/ahmedmyalo/upwork-freelance-jobs-60k) | Ahmed Mayalou (ahmedmyalo) | [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) | job_stream_1500.parquet, job_stream_sample.json, skill_vocab.json, price_stats.json, outcome_priors.json |
| [Freelance Contracts Dataset (1.3 million entries)](https://www.kaggle.com/datasets/asaniczka/freelance-contracts-dataset-1-3-million-entries) | asaniczka | [ODC-By v1.0](https://opendatacommons.org/licenses/by/1-0/) | price_stats.json, outcome_priors.json |
| [Freelancer Success, Earnings and Churn Prediction](https://www.kaggle.com/datasets/sarveshchhetri/freelancer-success-earnings-and-churn-prediction) | sarveshchhetri | [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) | outcome_priors.json |
| [trial-1](https://www.kaggle.com/datasets/adityammantri/trial-1) | adityammantri | Unknown (none stated) | scam_lexicon.json (aggregate word statistics only, no rows or text) |

Apache 2.0 notice: the datasets marked Apache 2.0 are licensed under the Apache License,
Version 2.0. You may not use those files except in compliance with the License. They are
distributed on an "AS IS" basis, without warranties or conditions of any kind.
