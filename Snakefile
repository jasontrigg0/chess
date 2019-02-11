#this file hasn't been tested / run

PGN_FILE="/home/jtrigg/Downloads/lichess_db_standard_rated_2018-10.pgn"
PGN_FILE="/home/jtrigg/files/misc/KingBase2018-all.pgn"

#read PGN_FILE
"/tmp/moves.csv" <- PGN_FILE
    python3 pgn_to_moves.py


####opening book####

#filter moves for opening book
"/tmp/filtered_moves.csv" <- "/tmp/moves.csv"
    python3 filter_moves.py

#generate opening book
"%book" <- "/tmp/filtered_moves.csv"
    python3 opening_book.py



####move predictions####

#create rows for move prediction / analysis
"/tmp/pred_data.csv" <- "/tmp/moves.csv"
    python3 generate_prediction_data.py

#create features for prediction
"/tmp/chess_features.csv" <- "/tmp/pred_data.csv"
    python3 compute_features.py

#generate prediction
"%regression" <- "/tmp/chess_features.csv"
    less /tmp/chess_features.csv | pcsv -p 'r["abs_eval"] = abs(int(r["eval"]))' | pcsv -p 'r["best_move"] = 1* ( r["loss"] == "0" )' | linreg -c elo,abs_eval -t loss
    less /tmp/chess_features.csv | pcsv -p 'r["abs_eval"] = abs(int(r["eval"]))' | pcsv -p 'r["best_move"] = 1* ( r["loss"] == "0" )' | linreg -c loss,best_move -t elo


####game quality metric####

#step 1:
#find f ("loss score") such that f(loss) correlates best with elo
#eg: elo ~ loss, loss * eval**2, loss * loss_8, loss_sq, loss * (move_cnt < 10)

#less /tmp/chess_features.csv | pcsv -p 'r["abs_eval"] = abs(float(r["eval"])); r["negative_loss"] = 1*(float(r["loss"])<0); r["best_move"] = 1* ( r["loss"] == "0" ); r["loss_X_abs_eval"] = float(r["abs_eval"]) * float(r["loss"]); r["loss_X_eval_sq"] = (float(r["abs_eval"])**2) * float(r["loss"]); r["l2"] = float(r["loss"]) * (float(r["abs_eval"]) == 1000); r["loss_X_loss8"] = float(r["loss"]) * float(r["loss_8"]); r["move_cnt"] = float(r["loss"]) * (float(r["position"].split()[-1]) < 10); r["loss_sq"] = float(r["loss"])**2' | linreg -c loss,loss_X_eval_sq,loss_X_loss8,move_cnt,loss_sq -t elo --so > /tmp/preds1.csv

#step 2:
#best prediction g ("expected_loss_score") for g(position,elo) = f(loss)
#eg: f(loss) ~ abs(eval), elo, loss_8

#less /tmp/preds1.csv | pagg -c elo -a mean --append | pcsv -p 'r["loss_score"] = float(r["pred"])' | pcsv -C pred,error | linreg -c abs_eval,elo,loss_0,loss_1,loss_2,loss_4,loss_8 -t loss_score --so > /tmp/preds2.csv

#step 3: (may not matter much?)
#best prediction h(position) = (f(loss) - g(position, mean elo))**2
#eg: (f(loss) - g(position, mean elo))**2 ~ abs_eval

#READ COEFF FROM step 2 regression coefficient of *elo* variable
#COEFF=0.002855160255518508; less /tmp/preds2.csv | pcsv -p 'r["expected_loss_score"] = float(r["pred"]) - '"$COEFF"' * (float(r["elo"]) - float(r["elo_mean"])); r["adjusted_loss_score"] = float(r["loss_score"]) - float(r["expected_loss_score"])' | pcsv -C pred,error  | pcsv -p 'r["als_var"] = float(r["adjusted_loss_score"])**2' | linreg -c abs_eval -t als_var --so | pcsv -p 'r["weight"] = 1 / float(r["pred"])' | pcsv -C pred,error > /tmp/preds3.csv


less /tmp/preds3.csv | pcsv -p 'r["move_score"] = float(r["weight"]) * float(r["adjusted_loss_score"])'


#step 4:
#game score = weighted mean of   (  f(loss) - g(position, mean elo)  ) with weights 1/h(position)

#possible step 5?
#ie game score = sum( f(loss) - g(position, mean elo) ) / (sum(weights) + pseudocounts)
#to downweight fast draws
