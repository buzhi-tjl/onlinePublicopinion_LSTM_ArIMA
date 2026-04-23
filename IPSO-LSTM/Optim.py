# -*- coding: utf-8 -*-
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from model import LSTM_
import math
plt.rcParams['font.family'] = ['sans-serif']
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus']=False

def fitness(pop,P,T,Pt,Tt):
    
    tf.random.set_seed(0)
    lr = pop[0]  
    num_epochs = int(pop[1])  
    batch_size = int(pop[2])  
    hidden1 = int(pop[3])  
    hidden2 = int(pop[4])  
    fc = int(pop[5]) 
    sequence, feature = P.shape[-2:]
    output_node = T.shape[1]
    
    model = LSTM_(sequence, feature,hidden1,hidden2, fc, output_node).build_model()
    
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=lr), loss='mse')
    
    model.fit(P, T, 
              epochs=num_epochs,batch_size=batch_size, verbose=2)
    
    Tp = model.predict(Pt)
        
    F2=np.mean(np.square((Tp-Tt)))
    return F2




def IPSO(train_X, train_Y, valid_X, valid_Y):
    lb = [0.001,10, 16, 1 ,1 ,1]
    ub = [0.01, 100,128,20,20,100]
    dim = len(lb)  
    pN = 5
    max_iter = 10
    c1 = 1.6;
    c2 = 1.4;
    r1 = 0.7;
    r2 = 0.5
    wmax = 0.9;
    wmin = 0.7

    X = np.zeros((pN, dim))
    V = np.zeros((pN, dim))
    pbest = np.zeros((pN, dim))
    gbest = np.zeros((1, dim))
    p_fit = np.zeros(pN)
    result = np.zeros((max_iter, dim))
    fit = np.inf
    for i in range(pN):
        for j in range(dim):
            if j == 0:  
                X[i][j] = (ub[j] - lb[j]) * np.random.rand() + lb[j]
            else:
                X[i][j] = np.random.randint(lb[j], ub[j])
            V[i][j] = np.random.rand()
        pbest[i] = X[i].copy()
        tmp = fitness(X[i, :], train_X, train_Y, valid_X, valid_Y)
        p_fit[i] = tmp
        if (tmp < fit):
            fit = tmp
            gbest = X[i]
    trace = []
    for t in range(max_iter):

        w = wmax - (wmax - wmin) * np.tanh(np.pi / 4 * t / max_iter)

        for i in range(pN):
            V[i, :] = w * V[i, :] + c1 * r1 * (pbest[i] - X[i, :]) + c2 * r2 * (gbest - X[i, :])
            X[i, :] = X[i, :] + V[i, :]
            X[i, :] = boundary(X[i, :], lb, ub)  
            prob = 0.5 * t / max_iter + 0.5  
            if np.random.rand() > prob:
                for j in range(dim):
                    if j == 0:
                        X[i][j] = (ub[j] - lb[j]) * np.random.rand() + lb[j]
                    else:
                        X[i][j] = np.random.randint(lb[j], ub[j])

        for i in range(pN):  
            temp = fitness(X[i, :], train_X, train_Y, valid_X, valid_Y)
            if (temp < p_fit[i]): 
                p_fit[i] = temp
                pbest[i, :] = X[i, :]
                if (p_fit[i] < fit): 
                    gbest = X[i, :].copy()
                    fit = p_fit[i].copy()
        result[t, :] = gbest.copy()
        trace.append(fit)
        print(t, fit, [int(gbest[i]) if i > 0 else gbest[i] for i in range(len(lb))])
    return trace, gbest, result

def boundary(pop,lb,ub):
    pop=[int(pop[i]) if i>0 else pop[i] for i in range(len(lb))]
    for i in range(len(lb)):
        if pop[i]>ub[i] or pop[i]<lb[i]:
            if i==0:
                pop[i] = (ub[i]-lb[i])*np.random.rand()+lb[i]
            else:
                pop[i] = np.random.randint(lb[i],ub[i])
    return pop

    
    