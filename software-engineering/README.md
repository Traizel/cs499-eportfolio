# Software Engineering and Design

The CS 340 AnimalShelter CRUD module is preserved in original/CRUD_Python.py. The enhanced package separates validation, configuration, service logic, repository access, results, and errors. Source files are unchanged from the supplied milestone.

## Run the offline checks

Use Python 3.10 or newer; final checks used Python 3.12. From this category folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r enhanced/requirements.txt
cd enhanced
python -m unittest discover -s tests -v
python demo.py
```

The suite has 31 tests. The demo uses an in-memory repository. Neither requires a running MongoDB server after installing the dependencies.

## Migration and design

| Original behavior | Enhanced behavior | Caller change |
| --- | --- | --- |
| Class creates its database connection | Service receives a repository | Construct the appropriate repository and inject it |
| Read returns a list or hides a failure | Controlled errors distinguish failure from no matches | Handle the documented exceptions |
| Updates and deletes can use broad filters | Mutations require a unique MongoDB record ID | Read/select the target ID before mutation |
| Basic operation return values | Typed result objects preserve matched and modified counts | Read the relevant result fields |
| Credentials supplied to the original constructor | Environment-based configuration | Set MONGODB_URI outside source control |

The service owns its repository and closes it on context exit. See enhanced/demo.py for the working interface and enhanced/animal_shelter/repository.py for the repository contract.

## Live reads and limitations

For an existing authorized database, configure MONGODB_URI, MONGODB_DATABASE (default aac), and MONGODB_COLLECTION (default animals), then run python live_read.py from enhanced. Keep credentials out of source files and Git history. Application validation does not establish database permissions. The later databases category contains separate live verification on generated data.

The final offline log is evidence/final-test-results.txt. Milestone evidence is retained alongside it. The narrative and final review guide explain scope and tradeoffs.
