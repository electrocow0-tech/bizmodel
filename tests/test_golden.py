import csv

from bizmodel.golden import COLUMNS, answered


def write(path, answers):
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS)
        writer.writeheader()
        for answer in answers:
            writer.writerow({column: "x" for column in COLUMNS} | {"ответ": answer})


def test_fresh_table_has_no_answers(tmp_path):
    path = tmp_path / "labels.csv"
    assert answered(path) == 0
    write(path, ["", " ", ""])
    assert answered(path) == 0


def test_table_with_answers_is_recognised(tmp_path):
    path = tmp_path / "labels.csv"
    write(path, ["да", "", "не знаю"])
    assert answered(path) == 2
