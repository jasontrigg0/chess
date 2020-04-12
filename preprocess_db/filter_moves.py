import csv

#filter a list of moves to include only positions with
#a minimum number of occurrences

if __name__ == "__main__":
    #filter to have only the move histories with a minimum frequency (TODO: use zobrist hashes instead)
    MIN_CNT = 20

    cnts = {}

    #read through the file twice
    with open("/tmp/moves.csv") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            cnts[row["move_history"]] = cnts.setdefault(row["move_history"],0) + 1

    with open("/tmp/filtered_moves.csv", 'w') as csvfile:
        fieldnames = ["start_fen", "move_history", "move"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        with open("/tmp/moves.csv") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if cnts[row["move_history"]] >= MIN_CNT:
                    writer.writerow({"start_fen":row["fen"], "move_history": row["move_history"], "move":row["move"]})
