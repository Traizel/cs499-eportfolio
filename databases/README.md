# Database Enhancement

The unchanged CS 340 source is original/CRUD_Python_Module.py. The enhanced package retains the software engineering layer and adds validated search, projection, stable sorting, offset pagination, rescue summaries, explicit index creation, and explain diagnostics.

## Run the offline checks

Use Python 3.10 or newer. From this category folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r enhanced/requirements.txt
cd enhanced
python -m unittest discover -s tests -v
python database_demo.py
```

There are 45 tests: the earlier 31 plus 14 database tests. The policy demo prints query specifications and aggregation structure; it is not a live server test.

## Live operations

Configure MONGODB_URI outside source control. Optional environment variables are MONGODB_DATABASE (default aac), MONGODB_COLLECTION (default animals), and MONGODB_TIMEOUT_MS (default 5000). From enhanced, python setup_indexes.py creates the rescue_filter_v1 compound index and python live_read.py performs a read. Index setup requires appropriate administration permissions and is separate from ordinary application reads.

The optional python live_verify.py --output live_results.json verification creates an isolated temporary collection containing generated records, exercises it, and drops that temporary collection afterward. Run it only against a local/test database with permission to create and drop its test collection; it requires writes and index administration. It does not benchmark the real AAC dataset.

## Query policy and tradeoffs

Only approved scalar filters, field names, sort directions, and finite age bounds are accepted. Pages are 1 to 100 records, and offsets above 100000 are rejected. The query fetches one additional record to compute has_next. A unique _id resolves sort ties, but independent page requests do not form a consistent snapshot during concurrent writes. Deep offset pages still become expensive.

Default rescue summaries assign overlapping matches in water, mountain, disaster order; an explicit category uses that category's rules. Presets identify candidates, not verified rescue suitability. The compound index consumes storage and write-maintenance work and does not optimize every query or sort.

## Evidence

evidence/final-test-results.txt is the new offline run. evidence/live_results.json and live_output.txt are retained Milestone Four results, not a newly repeated live experiment. The prior generated-data workload returned the same 100 candidates before and after indexing while documents examined changed from 10000 to 100. Reported time changed from 2 ms to 0 ms; rounding and explain behavior limit latency conclusions. MongoDB server permissions and representative production workloads need separate verification.
