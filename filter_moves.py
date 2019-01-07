import csv

#filter a list of moves to include only positions with
#a minimum number of occurrences

if __name__ == "__main__":
    #filter to have only the zobrist hashs with a minimum frequency
    MIN_CNT = 20

    cnts = {}

    #read through the file twice
    with open("/tmp/moves.csv") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            cnts[row["zobrist"]] = cnts.setdefault(row["zobrist"],0) + 1

    with open("/tmp/filtered_moves.csv", 'w') as csvfile:
        fieldnames = ["zobrist", "start_fen", "previous_moves", "move"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        with open("/tmp/moves.csv") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if cnts[row["zobrist"]] >= MIN_CNT:
                    writer.writerow({"zobrist":row["zobrist"], "start_fen":row["start_fen"], "previous_moves": row["previous_moves"], "move":row["move"]})
