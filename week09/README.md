# Week 09: OLTP, OLAP and Pivot

## Setup

Install the required Python package:

```bash
python -m pip install -r requirements.txt
```

## Run the lab

Generate or reset the lab data:

```bash
python lab.py --reset
```

Run the SQL query runner:

```bash
python query.py data/warehouse.db queries.sql
```

The SQL answers are stored in `q01.sql` through `q12.sql`. The main scripts are:

- `lab.py`: generates the lab data.
- `oltp_demo.py`: demonstrates the OLTP workflow.
- `pivot_student.py`: creates the pivot analysis.
- `query.py`: runs SQL files against SQLite databases.

See [README_TH.md](README_TH.md) for the Thai instructions.

## Author

Pannakorn Polasen (67160352)