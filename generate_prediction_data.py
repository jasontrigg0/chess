import csv

INPUT_FILE = "/tmp/moves_test.csv"
OUTPUT_FILE = "/tmp/pred_data.csv"

#TODO: include this feature:
#https://ailab.si/matej/doc/Computer_Analysis_of_World_Chess_Champions.pdf
if __name__ == "__main__":
    fout = open(OUTPUT_FILE, 'w')
    fieldnames = ['position','move','elo', 'opp_elo','result'] #['eval', 'loss']
    writer = csv.DictWriter(fout, fieldnames=fieldnames)
    writer.writeheader()

    with open(INPUT_FILE) as fin:
        reader = csv.DictReader(fin)
        for row in reader:
            #convert eval, loss to the perspective of the player to play
            white_turn = row["fen"].split()[1] == "w"
            if (row["result"]) == "*": continue

            result_val = {
                "0-1": 0,
                "1/2-1/2":0.5,
                "1-0":1
            }[row["result"]]
            result = result_val if white_turn else (1-result_val)

            if white_turn:
                elo = row["white_elo"]
                opp_elo = row["black_elo"]
            else:
                elo = row["black_elo"]
                opp_elo = row["white_elo"]

            outrow = {
                "position":row["fen"],
                "move":row["move"],
                "elo":elo,
                "opp_elo":opp_elo,
                "result":result
            }

            #print(best_move, row["move"], outrow)
            writer.writerow(outrow)
