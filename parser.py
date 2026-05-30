# parser.py
import re
import hashlib
from dataclasses import dataclass
from typing import Optional
from datetime import date

DATE_HEADER  = re.compile(r'^\s*(\d{1,2})/(\d{1,2})\s*$')
EXPENSE_ROW  = re.compile(r'^\s*([0-9]*[.,]?\d+)\s+(.+?)\s*$')
AMOUNT_ONLY  = re.compile(r'^\s*([0-9]*[.,]?\d+)\s*$')
YEAR_IN_NAME = re.compile(r'(\d{4})')

@dataclass
class ParsedRow:
    date: date
    amount: float
    description: str
    raw_line: str
    source_file: str
    category: Optional[str] = None
    subcategory: Optional[str] = None

@dataclass
class ConflictRow:
    raw_line: str
    source_file: str
    issue: str
    context_date: Optional[date]
    content_hash: str

def extract_year(filename: str) -> Optional[int]:
    match = YEAR_IN_NAME.search(filename)
    return int(match.group(1)) if match else None

def make_hash(raw_line: str, row_date: Optional[date]) -> str:
    key = f"{raw_line.strip()}|{str(row_date)}"
    return hashlib.md5(key.encode()).hexdigest()

def parse_txt(filepath: str) -> tuple[list[ParsedRow], list[ConflictRow]]:
    source_file = filepath.split("/")[-1]
    year = extract_year(source_file)
    if year is None:
        raise ValueError(f"Could not extract year from filename: {source_file}")

    parsed    = []
    conflicts = []
    current_date = None

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # date header
        date_match = DATE_HEADER.match(line)
        if date_match:
            day, month = int(date_match.group(1)), int(date_match.group(2))
            try:
                current_date = date(year, month, day)
            except ValueError:
                conflicts.append(ConflictRow(
                    raw_line=line,
                    source_file=source_file,
                    issue=f"Invalid date value: {line}",
                    context_date=None,
                    content_hash=make_hash(line, None)
                ))
            continue

        # amount only — no description
        if AMOUNT_ONLY.match(line):
            conflicts.append(ConflictRow(
                raw_line=line,
                source_file=source_file,
                issue="Amount with no description — possible accidental line break",
                context_date=current_date,
                content_hash=make_hash(line, current_date)
            ))
            continue

        # full expense row
        expense_match = EXPENSE_ROW.match(line)
        if expense_match:
            amount = float(expense_match.group(1).replace(",", "."))
            if current_date is None:
                conflicts.append(ConflictRow(
                    raw_line=line,
                    source_file=source_file,
                    issue="Expense row found before any date header",
                    context_date=None,
                    content_hash=make_hash(line, None)
                ))
                continue

            parsed.append(ParsedRow(
                date=current_date,
                amount=amount,
                description=expense_match.group(2),
                raw_line=line,
                source_file=source_file,
                category=None,
                subcategory=None,
            ))
            continue

        # anything else
        conflicts.append(ConflictRow(
            raw_line=line,
            source_file=source_file,
            issue="Could not parse as date header or expense row",
            context_date=current_date,
            content_hash=make_hash(line, current_date)
        ))

    return parsed, conflicts

def parse_contents(contents: str, filename: str) -> tuple[list[ParsedRow], list[ConflictRow]]:
    year = extract_year(filename)
    if year is None:
        raise ValueError(f"Could not extract year from filename: {filename}")

    parsed    = []
    conflicts = []
    current_date = None

    for raw_line in contents.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        date_match = DATE_HEADER.match(line)
        if date_match:
            day, month = int(date_match.group(1)), int(date_match.group(2))
            try:
                current_date = date(year, month, day)
            except ValueError:
                conflicts.append(ConflictRow(
                    raw_line=line,
                    source_file=filename,
                    issue=f"Invalid date value: {line}",
                    context_date=None,
                    content_hash=make_hash(line, None)
                ))
            continue

        if AMOUNT_ONLY.match(line):
            conflicts.append(ConflictRow(
                raw_line=line,
                source_file=filename,
                issue="Amount with no description — possible accidental line break",
                context_date=current_date,
                content_hash=make_hash(line, current_date)
            ))
            continue

        expense_match = EXPENSE_ROW.match(line)
        if expense_match:
            amount = float(expense_match.group(1).replace(",", "."))
            parsed.append(ParsedRow(
                date=current_date,
                amount=amount,
                description=expense_match.group(2),
                raw_line=line,
                source_file=filename,
            ))
            continue

        conflicts.append(ConflictRow(
            raw_line=line,
            source_file=filename,
            issue="Could not parse as date header or expense row",
            context_date=current_date,
            content_hash=make_hash(line, current_date)
        ))

    return parsed, conflicts