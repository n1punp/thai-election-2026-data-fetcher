# Thailand Election Data (2569 BE / 2026 CE)

Fetches Thailand's general election and referendum data from official sources.

## Data Sources

| Source | URL | Data |
|--------|-----|------|
| ECT (Election Commission) | https://ectreport69.ect.go.th | Election results, referendum results |
| Vote62 | https://www.vote62.com | Candidate ballot numbers, party ballot numbers |

## Project Structure

```
.
├── src/                    # Python scripts
│   ├── fetch_election.py       # Fetches ECT election data
│   ├── fetch_vote62_candidates.py  # Fetches Vote62 ballot numbers
│   ├── merge_election_data.py  # Merges ECT + Vote62 data
├── data/                   # Output data files (CSV, JSON)
├── reports/                # Human-readable reports (TXT)
├── run.sh                  # Run all scripts
└── README.md
```

## Quick Start

```bash
# Install dependencies
uv pip install httpx

# Run all scripts
./run.sh

# Or run individually:
uv run --with httpx python src/fetch_election.py
uv run --with httpx python src/fetch_vote62_candidates.py
uv run python src/merge_election_data.py
```

## Scripts

### 1. `src/fetch_election.py`
Fetches election results from ECT (Election Commission of Thailand).

**Data collected per constituency:**
- สส.แบ่งเขต (Constituency MP): turnout, valid/invalid/blank votes, all candidates with scores
- บัญชีรายชื่อ (Party List): turnout, valid/invalid/blank votes, all parties with scores
- ประชามติ (Referendum): turnout, valid/invalid votes, yes/no/abstain results

**Output files:**
| File | Description |
|------|-------------|
| `data/election_data.json` | Complete raw data |
| `data/constituency_details.csv` | All candidates & party-list votes per constituency |
| `data/constituency_summary.csv` | One row per constituency with winner info |
| `data/referendum_details.csv` | Referendum results per constituency |
| `reports/election_report.txt` | Human-readable formatted report |

### 2. `src/fetch_vote62_candidates.py`
Fetches candidate and party ballot numbers from Vote62.

**Output files:**
| File | Description |
|------|-------------|
| `data/vote62_candidates.csv` | All สส.เขต candidates with ballot numbers |
| `data/vote62_by_constituency.csv` | One row per constituency, candidates in columns |
| `data/vote62_party_numbers.csv` | Party ballot numbers (เบอร์พรรค) |
| `reports/vote62_candidates_report.txt` | Human-readable formatted report |
| `data/vote62_data.json` | Complete raw data |

### 3. `src/merge_election_data.py`
Merges ECT election results with Vote62 ballot numbers.

**Output files:**
| File | Description |
|------|-------------|
| `data/constituency_details_augmented.csv` | Election results + ballot numbers |

## Output Data Schema

### `data/constituency_details_augmented.csv`

| Column | Description |
|--------|-------------|
| `province` | จังหวัด |
| `prov_id` | รหัสจังหวัด |
| `cons_id` | รหัสเขต (e.g., BKK_1) |
| `cons_no` | หมายเลขเขต |
| `zones` | พื้นที่ในเขต |
| `registered_voters` | ผู้มีสิทธิเลือกตั้ง |
| `cons_turnout` | ผู้มาใช้สิทธิ (สส.แบ่งเขต) |
| `cons_turnout_pct` | % ผู้มาใช้สิทธิ |
| `cons_valid` | บัตรดี |
| `cons_invalid` | บัตรเสีย |
| `cons_blank` | บัตรไม่เลือกผู้ใด |
| `party_list_turnout` | ผู้มาใช้สิทธิ (บัญชีรายชื่อ) |
| `party_list_turnout_pct` | % ผู้มาใช้สิทธิ |
| `party_list_valid` | บัตรดี |
| `party_list_invalid` | บัตรเสีย |
| `party_list_blank` | บัตรไม่เลือกผู้ใด |
| `type` | ประเภท: สส.แบ่งเขต / บัญชีรายชื่อ |
| `rank` | ลำดับคะแนน |
| `candidate_ballot_no` | เบอร์ผู้สมัคร |
| `candidate_name` | ชื่อผู้สมัคร |
| `party_ballot_no` | เบอร์พรรค |
| `party_name` | ชื่อพรรค |
| `party_abbr` | ชื่อย่อพรรค |
| `votes` | คะแนน |
| `vote_pct` | % คะแนน |

### `data/referendum_details.csv`

| Column | Description |
|--------|-------------|
| `province` | จังหวัด |
| `cons_no` | หมายเลขเขต |
| `ref_turnout` | ผู้มาใช้สิทธิ |
| `ref_turnout_pct` | % ผู้มาใช้สิทธิ |
| `ref_valid` | บัตรดี |
| `ref_invalid` | บัตรเสีย |
| `yes_votes` | เห็นชอบ |
| `yes_pct` | % เห็นชอบ |
| `no_votes` | ไม่เห็นชอบ |
| `no_pct` | % ไม่เห็นชอบ |
| `abstained` | ไม่แสดงความเห็น |
| `abstained_pct` | % ไม่แสดงความเห็น |

### `data/vote62_party_numbers.csv`

| Column | Description |
|--------|-------------|
| `party_no` | เบอร์พรรค |
| `party_name` | ชื่อพรรค |
| `resign` | สถานะลาออก |

## Election Results Summary (2569)

### Overall Statistics
- **Registered voters:** 52,922,923
- **Turnout:** 34,632,581 (65.44%)
- **Valid votes:** 31,951,912
- **Invalid votes:** 1,234,047
- **Blank votes:** 1,446,622

### Top Parties (Party List)
| Rank | Party | Votes | % | Seats |
|------|-------|-------|---|-------|
| 1 | ประชาชน | 9,802,658 | 28.30% | 87 |
| 2 | ภูมิใจไทย | 5,964,814 | 17.22% | 174 |
| 3 | เพื่อไทย | 5,158,066 | 14.89% | 58 |
| 4 | ประชาธิปัตย์ | 3,662,606 | 10.58% | 10 |
| 5 | กล้าธรรม | 606,312 | 1.75% | 56 |

### Referendum Results
- **Question:** ท่านเห็นชอบว่าสมควรมีรัฐธรรมนูญฉบับใหม่หรือไม่
- **YES:** 19,978,736 (59.77%)
- **NO:** 10,553,327 (31.57%)
- **Abstain:** 2,891,465 (8.65%)

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- httpx

## License

Data is from public government sources. Use responsibly.
