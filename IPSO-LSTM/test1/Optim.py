# Optim.py (IPSO-LSTM-ARIMA 升级版)
import numpy as np
import tensorflow as tf
from tensorflow.keras.optimizers import Adam
from model import build_ehdan_model, apply_vmd, apply_ssd, split_sequence, normalize_data
import random
import warnings
from statsmodels.tsa.arima.model import ARIMA  # 新增ARIMA依赖
warnings.filterwarnings('ignore')

def fitness_arima(params, P, T, Pt, Tt, seq_len, n_outputs, scaler_y, verbose=False):
    """
    适配ARIMA融合的适应度函数：LSTM预测 + ARIMA残差修正
    Args:
        params: [lr, epochs, batch_size, lstm_units, time_dim, attn_heads, p, d, q]
                新增ARIMA的p(自回归阶数), d(差分阶数), q(移动平均阶数)
    Returns:
        val_loss: 融合模型的验证集MSE损失
    """
    # 解包参数（前6个为LSTM参数，后3个为ARIMA参数）
    lr, epochs, batch_size, lstm_units, time_dim, attn_heads, p, d, q = params
    epochs = int(epochs)
    batch_size = int(batch_size)
    lstm_units = int(lstm_units)
    time_dim = int(time_dim)
    attn_heads = int(attn_heads)
    p = int(max(1, p))  # ARIMA参数约束为正整数
    d = int(max(0, d))
    q = int(max(1, q))

    # 1. 构建并训练LSTM模型
    n_features = P.shape[-1]
    model = build_ehdan_model(
        n_steps_in=seq_len,
        n_features=n_features,
        n_outputs=n_outputs,
        lstm_units=int(lstm_units),
        attn_heads=int(attn_heads)
    )
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=lr), loss='mse')
    model.fit(P, T, epochs=epochs, batch_size=batch_size, verbose=0)

    # 2. LSTM验证集预测
    lstm_pred = model.predict(Pt, verbose=0)
    
    # 3. 计算LSTM残差（反标准化后）
    # 反标准化真实值和预测值
    Tt_denorm = scaler_y.inverse_transform(Tt.reshape(-1, n_outputs))
    lstm_pred_denorm = scaler_y.inverse_transform(lstm_pred.reshape(-1, n_outputs))
    residual = Tt_denorm - lstm_pred_denorm  # 残差序列

    # 4. ARIMA拟合残差（取第一个输出维度为例，可扩展多维度）
    arima_pred = []
    for i in range(residual.shape[1]):  # 遍历每个输出维度
        res_seq = residual[:, i].flatten()
        try:
            # ARIMA建模残差
            arima_model = ARIMA(res_seq, order=(p, d, q))
            arima_res = arima_model.fit()
            res_pred = arima_res.predict()  # 残差预测
            arima_pred.append(res_pred)
        except:
            # 建模失败时用0填充残差预测
            arima_pred.append(np.zeros_like(res_seq))
    arima_pred = np.array(arima_pred).T

    # 5. LSTM + ARIMA残差修正
    final_pred_denorm = lstm_pred_denorm + arima_pred
    # 重新标准化（保证损失计算尺度一致）
    final_pred = scaler_y.transform(final_pred_denorm)

    # 6. 计算融合模型的MSE损失
    val_loss = np.mean((Tt - final_pred) ** 2)

    if verbose:
        print(f"Fusion Model Validation MSE: {val_loss:.6f}")
    return val_loss

def boundary_arima(pop, lb, ub):
    """适配ARIMA的边界处理函数"""
    for j in range(len(pop)):
        if pop[j] < lb[j]:
            pop[j] = lb[j] + np.random.rand() * (ub[j] - lb[j])
        elif pop[j] > ub[j]:
            pop[j] = lb[j] + np.random.rand() * (ub[j] - lb[j])
        # 确保整数变量（扩展ARIMA参数）
        # epochs, batch_size, lstm_units, time_dim, attn_heads, p, d, q
        if j in [1, 2, 3, 4, 5, 6, 7, 8]:
            pop[j] = int(pop[j])
    return pop

def IPSO_LSTM_ARIMA(func, P, T, Pt, Tt, seq_len, n_outputs, scaler_y, pN=10, max_iter=20):
    """
    改进粒子群优化的LSTM-ARIMA融合模型
    新增ARIMA参数搜索空间：p(1-5), d(0-2), q(1-5)
    """
    # 扩展超参数搜索空间 [lr, epochs, batch_size, lstm_units, time_dim, attn_heads, p, d, q]
    bounds = [
        (1e-4, 1e-2),   # learning rate
        (10, 100),      # epochs
        (16, 128),      # batch_size
        (32, 128),      # lstm_units
        (4, 16),        # time_dim
        (2, 8),         # attn_heads
        (1, 5),         # ARIMA p
        (0, 2),         # ARIMA d
        (1, 5)          # ARIMA q
    ]
    dim = len(bounds)
    
    # 初始化粒子群
    particles = []
    velocities = []
    personal_best_pos = []
    personal_best_val = []
    
    for _ in range(pN):
        particle = [random.uniform(bound[0], bound[1]) for bound in bounds]
        particles.append(particle)
        velocities.append([0] * dim)
        personal_best_pos.append(particle.copy())
        # 计算初始适应度
        fit_val = func(
            particle, P=P, T=T, Pt=Pt, Tt=Tt,
            seq_len=seq_len, n_outputs=n_outputs, scaler_y=scaler_y
        )
        personal_best_val.append(fit_val)
    
    # 全局最优初始化
    global_best_idx = np.argmin(personal_best_val)
    global_best_pos = personal_best_pos[global_best_idx].copy()
    global_best_val = personal_best_val[global_best_idx]
    
    trace = [global_best_val]
    all_results = {'particles': [], 'fitness': []}
    
    # IPSO核心参数
    w, c1, c2 = 0.7, 1.5, 1.5
    for iter in range(max_iter):
        all_results['particles'].append([p.copy() for p in particles])
        all_results['fitness'].append(personal_best_val.copy())
        
        for i in range(pN):
            # 更新速度和位置
            r1, r2 = random.random(), random.random()
            for d_idx in range(dim):
                velocities[i][d_idx] = (
                    w * velocities[i][d_idx] +
                    c1 * r1 * (personal_best_pos[i][d_idx] - particles[i][d_idx]) +
                    c2 * r2 * (global_best_pos[d_idx] - particles[i][d_idx])
                )
                particles[i][d_idx] += velocities[i][d_idx]
                # 边界约束
                particles[i][d_idx] = max(bounds[d_idx][0], min(bounds[d_idx][1], particles[i][d_idx]))
            
            # 边界处理（整数约束）
            particles[i] = boundary_arima(particles[i], [b[0] for b in bounds], [b[1] for b in bounds])
            
            # 计算新适应度
            new_fit = func(
                particles[i], P=P, T=T, Pt=Pt, Tt=Tt,
                seq_len=seq_len, n_outputs=n_outputs, scaler_y=scaler_y
            )
            
            # 更新个体最优
            if new_fit < personal_best_val[i]:
                personal_best_val[i] = new_fit
                personal_best_pos[i] = particles[i].copy()
                
                # 更新全局最优
                if new_fit < global_best_val:
                    global_best_val = new_fit
                    global_best_pos = particles[i].copy()
        
        trace.append(global_best_val)
        print(f"Iteration {iter+1}/{max_iter}, Best Fitness: {global_best_val:.6f}")
    
    return trace, global_best_pos, all_results

# 保留原有LSTM的IPSO函数（兼容旧逻辑）
def fitness(params, P, T, Pt, Tt, seq_len, n_outputs, scaler_y, verbose=False):
    """原有纯LSTM适应度函数"""
    lr, epochs, batch_size, lstm_units, time_dim, attn_heads = params
    epochs = int(epochs)
    batch_size = int(batch_size)
    lstm_units = int(lstm_units)
    time_dim = int(time_dim)
    attn_heads = int(attn_heads)
    
    n_features = P.shape[-1]
    model = build_ehdan_model(
        n_steps_in=seq_len,
        n_features=n_features,
        n_outputs=n_outputs,
        lstm_units=int(lstm_units),
        attn_heads=int(attn_heads)
    )
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=lr), loss='mse')
    model.fit(P, T, epochs=epochs, batch_size=batch_size, verbose=0)
    
    val_pred = model.predict(Pt, verbose=0)
    val_loss = np.mean((Tt - val_pred) ** 2)
    
    if verbose:
        print(f"Validation MSE: {val_loss:.6f}")
    
    return val_loss

def boundary(pop, lb, ub):
    """原有边界处理函数"""
    for j in range(len(pop)):
        if pop[j] < lb[j]:
            pop[j] = lb[j] + np.random.rand() * (ub[j] - lb[j])
        elif pop[j] > ub[j]:
            pop[j] = lb[j] + np.random.rand() * (ub[j] - lb[j])
        if j in [1, 2, 3, 4, 5]:
            pop[j] = int(pop[j])
    return pop

def IPSO(func, P, T, Pt, Tt, seq_len, n_outputs, scaler_y, pN=10, max_iter=20):
    """原有纯LSTM的IPSO函数"""
    bounds = [
        (1e-4, 1e-2),   # learning rate
        (10, 100),      # epochs
        (16, 128),      # batch_size
        (32, 128),      # lstm_units
        (4, 16),        # time_dim
        (2, 8)          # attn_heads
    ]
    dim = len(bounds)
    
    particles = []
    velocities = []
    personal_best_pos = []
    personal_best_val = []
    
    for _ in range(pN):
        particle = [random.uniform(bound[0], bound[1]) for bound in bounds]
        particles.append(particle)
        velocities.append([0] * dim)
        personal_best_pos.append(particle.copy())
        fit_val = func(
            particle, P=P, T=T, Pt=Pt, Tt=Tt,
            seq_len=seq_len, n_outputs=n_outputs, scaler_y=scaler_y
        )
        personal_best_val.append(fit_val)
    
    global_best_idx = np.argmin(personal_best_val)
    global_best_pos = personal_best_pos[global_best_idx].copy()
    global_best_val = personal_best_val[global_best_idx]
    
    trace = [global_best_val]
    all_results = {'particles': [], 'fitness': []}
    
    w, c1, c2 = 0.7, 1.5, 1.5
    for iter in range(max_iter):
        all_results['particles'].append([p.copy() for p in particles])
        all_results['fitness'].append(personal_best_val.copy())
        
        for i in range(pN):
            r1, r2 = random.random(), random.random()
            for d in range(dim):
                velocities[i][d] = (
                    w * velocities[i][d] +
                    c1 * r1 * (personal_best_pos[i][d] - particles[i][d]) +
                    c2 * r2 * (global_best_pos[d] - particles[i][d])
                )
                particles[i][d] += velocities[i][d]
                particles[i][d] = max(bounds[d][0], min(bounds[d][1], particles[i][d]))
            
            particles[i] = boundary(particles[i], [b[0] for b in bounds], [b[1] for b in bounds])
            
            new_fit = func(
                particles[i], P=P, T=T, Pt=Pt, Tt=Tt,
                seq_len=seq_len, n_outputs=n_outputs, scaler_y=scaler_y
            )
            
            if new_fit < personal_best_val[i]:
                personal_best_val[i] = new_fit
                personal_best_pos[i] = particles[i].copy()
                
                if new_fit < global_best_val:
                    global_best_val = new_fit
                    global_best_pos = particles[i].copy()
        
        trace.append(global_best_val)
        print(f"Iteration {iter+1}/{max_iter}, Best Fitness: {global_best_val:.6f}")
    
    return trace, global_best_pos, all_results