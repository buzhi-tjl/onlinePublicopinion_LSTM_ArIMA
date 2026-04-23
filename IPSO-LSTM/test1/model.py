# model.py (完整版)
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error
import tensorflow as tf
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, LSTM, Dense, Bidirectional, Layer, Dropout, MultiHeadAttention
import warnings
warnings.filterwarnings('ignore')

# --- 新增依赖 ---
# 请确保已安装: pip install vmdpy PyEMD
try:
    from vmdpy import VMD
except ImportError:
    print("Warning: vmdpy not found. VMD decomposition will use placeholder.")

try:
    from PyEMD import VMD as PyEMD_VMD
    from PyEMD import SSD as PyEMD_SSD
except ImportError:
    print("Warning: PyEMD not found. VMD/SSD decomposition will use placeholder.")

# --- 定义 Time2Vec 层 ---
class Time2Vec(tf.keras.layers.Layer):
    def __init__(self, kernel_size):
        super(Time2Vec, self).__init__()
        self.kernel_size = kernel_size

    def build(self, input_shape):
        # 偏置项权重
        self.wb = self.add_weight(
            name='wb',
            shape=(input_shape[-1],),
            initializer='uniform',
            trainable=True
        )
        self.bb = self.add_weight(
            name='bb',
            shape=(),
            initializer='uniform',
            trainable=True
        )
        # 周期项权重
        self.wa = self.add_weight(
            name='wa',
            shape=(input_shape[-1], self.kernel_size),
            initializer='uniform',
            trainable=True
        )
        self.ba = self.add_weight(
            name='ba',
            shape=(self.kernel_size,),
            initializer='uniform',
            trainable=True
        )
        super(Time2Vec, self).build(input_shape)

    def call(self, inputs, **kwargs):
        # 偏置部分: (batch, features) -> (batch, features, 1)
        bias = tf.expand_dims(self.wb * inputs + self.bb, axis=-1)
        # 周期部分: (batch, kernel_size)
        wgts = tf.sin(tf.tensordot(inputs, self.wa, axes=[[1], [0]]) + self.ba)
        wgts = tf.expand_dims(wgts, axis=1)  # (batch, 1, kernel_size)
        # 拼接偏置项和周期项
        return tf.concat([bias[..., 0], wgts[:, 0, :]], axis=-1)

    def compute_output_shape(self, input_shape):
        return (input_shape[0], self.kernel_size + input_shape[-1])

# --- 辅助函数 ---
def create_time_features(df, time_col='datetime'):
    """从时间戳中提取时间特征"""
    df = df.copy()
    df[time_col] = pd.to_datetime(df[time_col])
    
    # 提取基础时间特征
    df['hour'] = df[time_col].dt.hour
    df['day_of_week'] = df[time_col].dt.dayofweek
    df['day_of_month'] = df[time_col].dt.day
    df['month'] = df[time_col].dt.month
    df['is_weekend'] = df['day_of_week'].apply(lambda x: 1 if x >= 5 else 0)
    
    # 可扩展：添加节假日特征、小时余弦/正弦编码等
    df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
    
    return df

def create_multistep_dataset(X, n_steps_in, n_steps_out):
    """
    将序列数据转换为监督学习格式（多特征输出）
    X: 输入特征矩阵 (n_samples, n_features)
    n_steps_in: 输入时间步数
    n_steps_out: 输出时间步数
    返回:
        X_seq: (n_samples - n_steps_in - n_steps_out + 1, n_steps_in, n_features)
        y_seq: (n_samples - n_steps_in - n_steps_out + 1, n_steps_out, n_features)
    """
    X_seq = []
    y_seq = []
    
    # 计算有效样本数
    n_samples = len(X) - n_steps_in - n_steps_out + 1
    if n_samples <= 0:
        raise ValueError(f"数据长度不足，至少需要 {n_steps_in + n_steps_out} 个样本")
    
    for i in range(n_samples):
        X_seq.append(X[i:i+n_steps_in])    # 过去 n_steps_in 步
        y_seq.append(X[i+n_steps_in:i+n_steps_in+n_steps_out])  # 未来 n_steps_out 步
    
    return np.array(X_seq), np.array(y_seq)

def split_sequence(data, n_steps_in, n_steps_out):
    """
    将二维时序数据转换为适用于多步预测的监督学习格式（仅预测第一个特征）
    Args:
        data: 输入的二维 numpy 数组，形状为 (total_timesteps, n_features)
        n_steps_in: 用作输入的过去时间步数量
        n_steps_out: 需要预测的未来时间步数量
    Returns:
        X: 输入序列，形状为 (n_samples, n_steps_in, n_features)
        y: 目标序列，形状为 (n_samples, n_steps_out)
    """
    X, y = [], []
    n_samples = len(data) - n_steps_in - n_steps_out + 1
    
    if n_samples <= 0:
        raise ValueError(f"数据长度过短，至少需要 {n_steps_in + n_steps_out} 个数据点")
    
    for i in range(n_samples):
        # 输入：从 i 到 i+n_steps_in 的所有特征
        X.append(data[i:(i + n_steps_in), :])
        # 输出：从 i+n_steps_in 开始的未来 n_steps_out 个时间步的第一个特征
        y.append(data[(i + n_steps_in):(i + n_steps_in + n_steps_out), 0])
    
    return np.array(X), np.array(y)

def normalize_data(data, scaler=None):
    """标准化数据到 [0,1] 区间"""
    if scaler is None:
        scaler = MinMaxScaler(feature_range=(0, 1))
        data_norm = scaler.fit_transform(data)
    else:
        data_norm = scaler.transform(data)
    return data_norm, scaler

# --- 信号分解函数 ---
def apply_vmd(signal, K=5, alpha=2000, tau=0., DC=0, init=1, tol=1e-7):
    """
    应用变分模态分解 (VMD)，确保输出长度与输入一致
    Args:
        signal: 一维输入信号 (n_samples,)
        K: 分解的模态数
        alpha: 惩罚因子
        tau: 噪声容限
        DC: 是否包含直流分量
        init: 初始化方式
        tol: 收敛阈值
    Returns:
        components: 分解后的分量，形状为 (n_samples, K)
    """
    try:
        # 使用 PyEMD 的 VMD 实现
        vmd_func = PyEMD_VMD()
        imfs = vmd_func(signal, K, alpha, tau, DC, init, tol)
        components = np.array(imfs).T  # (n_samples, K)
    except (NameError, ImportError):
        # 降级方案：使用零矩阵占位
        print("Warning: VMD decomposition unavailable, using zero matrix")
        components = np.zeros((len(signal), K))
    
    # 确保输出长度与输入一致
    if len(components) != len(signal):
        print(f"VMD输出长度 {len(components)} 与输入长度 {len(signal)} 不一致，自动对齐")
        if len(components) < len(signal):
            # 填充缺失部分
            padding = np.tile(components[-1], (len(signal) - len(components), 1))
            components = np.vstack([components, padding])
        else:
            # 截断过长部分
            components = components[:len(signal)]
    
    return components

def apply_ssd(signal, max_imf=5):
    """
    应用奇异谱分解 (SSD)，确保输出长度与输入一致
    Args:
        signal: 一维输入信号 (n_samples,)
        max_imf: 最大IMF分量数
    Returns:
        components: 分解后的分量，形状为 (n_samples, max_imf)
    """
    try:
        # 使用 PyEMD 的 SSD 实现
        ssd_func = PyEMD_SSD()
        imfs = ssd_func(signal)
        # 确保分量数不超过 max_imf
        selected_imfs = imfs[:max_imf] if len(imfs) >= max_imf else imfs
        # 补充不足的分量为零
        while len(selected_imfs) < max_imf:
            selected_imfs.append(np.zeros_like(signal))
        components = np.array(selected_imfs).T  # (n_samples, max_imf)
    except (NameError, ImportError):
        # 降级方案：使用零矩阵占位
        print("Warning: SSD decomposition unavailable, using zero matrix")
        components = np.zeros((len(signal), max_imf))
    
    # 确保输出长度与输入一致
    if len(components) != len(signal):
        print(f"SSD输出长度 {len(components)} 与输入长度 {len(signal)} 不一致，自动对齐")
        if len(components) < len(signal):
            padding = np.tile(components[-1], (len(signal) - len(components), 1))
            components = np.vstack([components, padding])
        else:
            components = components[:len(signal)]
    
    return components

# --- 核心 EHDAN 模型 ---
def build_ehdan_model(n_steps_in, n_features, n_outputs, lstm_units=64, attn_heads=4):
    """
    构建带多头注意力的双向LSTM模型 (EHDAN)
    Args:
        n_steps_in: 输入时间步长度
        n_features: 输入特征数
        n_outputs: 输出时间步长度
        lstm_units: LSTM单元数
        attn_heads: 注意力头数
    Returns:
        tf.keras.Model: 编译前的模型
    """
    # 输入层
    input_layer = tf.keras.Input(shape=(n_steps_in, n_features), name='input')
    
    # 双向LSTM层
    bilstm_out = Bidirectional(LSTM(lstm_units, return_sequences=True))(input_layer)
    
    # 多头注意力层
    attn_out = MultiHeadAttention(
        num_heads=attn_heads,
        key_dim=n_features
    )(bilstm_out, bilstm_out)
    
    # Dropout正则化
    dropout_out = Dropout(0.2)(attn_out)
    
    # 全连接层
    flatten = tf.keras.layers.Flatten()(dropout_out)
    dense1 = Dense(128, activation='relu')(flatten)
    
    # 输出层（线性激活用于回归）
    output = Dense(n_outputs, activation='linear', name='output')(dense1)
    
    # 构建模型
    model = Model(inputs=input_layer, outputs=output)
    
    return model

# --- 评估函数 ---
def evaluate_metrics(real, pred):
    """
    计算回归评估指标
    Args:
        real: 真实值数组
        pred: 预测值数组
    Returns:
        dict: 包含MAPE、RMSE、MAE的字典
    """
    # 避免除零错误
    real = np.array(real)
    pred = np.array(pred)
    mask = real != 0
    
    # 计算MAPE（仅使用非零真实值）
    if np.any(mask):
        mape = np.mean(np.abs((real[mask] - pred[mask]) / real[mask])) * 100
    else:
        mape = np.nan
    
    # 计算RMSE和MAE
    rmse = np.sqrt(mean_squared_error(real, pred))
    mae = mean_absolute_error(real, pred)
    
    return {
        'MAPE': round(mape, 4),
        'RMSE': round(rmse, 4),
        'MAE': round(mae, 4)
    }

# --- 工具函数：反标准化预测结果 ---
def inverse_normalize_pred(pred, scaler, n_features):
    """
    反标准化预测结果（仅针对第一个特征）
    Args:
        pred: 标准化的预测值 (n_samples, n_outputs)
        scaler: 拟合过的MinMaxScaler
        n_features: 原始特征数
    Returns:
        pred_inv: 反标准化后的预测值
    """
    # 构造全零矩阵以匹配原始特征维度
    pred_reshaped = np.zeros((pred.shape[0], pred.shape[1], n_features))
    pred_reshaped[:, :, 0] = pred  # 仅填充目标特征
    
    # 反标准化
    pred_inv = []
    for i in range(pred.shape[1]):
        pred_inv.append(scaler.inverse_transform(pred_reshaped[:, i, :])[:, 0])
    
    return np.array(pred_inv).T

# --- 测试代码（可选） ---
if __name__ == "__main__":
    # 生成测试数据
    np.random.seed(42)
    test_data = np.random.rand(1000, 5)  # 1000个时间步，5个特征
    
    # 测试数据预处理
    n_steps_in = 24
    n_steps_out = 12
    X, y = split_sequence(test_data, n_steps_in, n_steps_out)
    print(f"输入序列形状: {X.shape}")
    print(f"目标序列形状: {y.shape}")
    
    # 测试标准化
    X_norm, scaler = normalize_data(X.reshape(-1, X.shape[-1]))
    X_norm = X_norm.reshape(-1, n_steps_in, X.shape[-1])
    print(f"标准化后输入形状: {X_norm.shape}")
    
    # 测试模型构建
    model = build_ehdan_model(
        n_steps_in=n_steps_in,
        n_features=X.shape[-1],
        n_outputs=n_steps_out,
        lstm_units=64,
        attn_heads=4
    )
    model.compile(optimizer='adam', loss='mse')
    model.summary()
    
    # 测试信号分解
    test_signal = test_data[:, 0]  # 取第一个特征作为测试信号
    vmd_components = apply_vmd(test_signal, K=5)
    ssd_components = apply_ssd(test_signal, max_imf=5)
    print(f"VMD分解结果形状: {vmd_components.shape}")
    print(f"SSD分解结果形状: {ssd_components.shape}")
    
    # 测试评估指标
    y_pred = np.random.rand(*y.shape)
    metrics = evaluate_metrics(y, y_pred)
    print("评估指标:", metrics)