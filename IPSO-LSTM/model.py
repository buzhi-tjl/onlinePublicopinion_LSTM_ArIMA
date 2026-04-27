import tensorflow.keras.backend as K
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Dense, LSTM,Input,Dropout, Bidirectional
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.regularizers import l2

def split_data(data, n):
    in_ = []
    out_ = []    
    N = data.shape[0] - n
    for i in range(N):
        in_.append(data[i:i + n,:])
        out_.append(data[i + n,:96])
    in_ = np.array(in_).reshape(len(in_), -1)
    out_ = np.array(out_).reshape(len(out_), -1)
    return in_, out_
def result(real,pred,name):
    ss_X = MinMaxScaler(feature_range=(-1, 1))
    real = ss_X.fit_transform(real).reshape(-1,)
    pred = ss_X.transform(pred).reshape(-1,)
    
    # mape
    test_new=[]
    predict_new=[]
    for k in range(len(real)):
        if real[k]!=0:
            test_new.append(real[k])
            predict_new.append(pred[k])
    test_new = np.asarray(test_new) 
    predict_new = np.asarray(predict_new)
    test_mape = np.mean(np.abs((predict_new - test_new) /test_new))
    #test_mape = np.mean(np.abs((pred - real) / real))
    # rmse
    test_rmse = np.sqrt(np.mean(np.square(pred - real)))
    # mae
    test_mae = np.mean(np.abs(pred - real))
   
    #print(name,':的mape:', test_mape, ' rmse:', test_rmse, ' mae:', test_mae)
    print(name,'的mape:%.4f,rmse:%.4f,mae：%.4f'%(test_mape,test_rmse,test_mae))


class LSTM_(object):
    def __init__(self, seq, feat_dim, hidden_unit1, hidden_unit2, fc, output_dim):
        self.input_dim = seq
        self.feat_dim = feat_dim
        self.units1 = hidden_unit1
        self.units2 = hidden_unit2
        self.fc = fc
        self.output_dim = output_dim

    def build_model(self):
        inp = Input(shape=(self.input_dim, self.feat_dim))
        
        # 第一层：双向LSTM + Dropout + L2正则
        lstm1 = Bidirectional(LSTM(
            self.units1, 
            return_sequences=True,
            kernel_regularizer=l2(1e-4),
            recurrent_regularizer=l2(1e-4)
        ))(inp)
        lstm1 = Dropout(0.3)(lstm1)
        
        # 第二层：双向LSTM + Dropout + L2正则
        lstm2 = Bidirectional(LSTM(
            self.units2, 
            return_sequences=False,
            kernel_regularizer=l2(1e-4),
            recurrent_regularizer=l2(1e-4)
        ))(lstm1)
        lstm2 = Dropout(0.3)(lstm2)
        
        # 全连接层
        dense = Dense(self.fc, activation='relu', kernel_regularizer=l2(1e-4))(lstm2)
        
        # 输出层：ReLU激活，强制非负输出
        out = Dense(self.output_dim, activation='relu')(dense)
        
        model = Model(inputs=inp, outputs=out)
        return model






