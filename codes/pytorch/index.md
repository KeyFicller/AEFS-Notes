# PyTorch 分阶段练习

练习放在 `codes/pytorch/{阶段目录}/qa.ipynb`。需要读写文件时，工作空间就是该阶段目录。

出题 / 审阅 / 出卡习惯对齐 `python-base-qa`：一次只做一个阶段；出题不写答案；出卡才生成该阶段的 `card.png`。

| 阶段 | 目录 | 焦点 |
| --- | --- | --- |
| 1 | `01_tensor_basics` | 创建、索引切片、shape / dtype / device、基础逐元素运算与简单归约 |
| 2 | `02_shape_broadcast` | reshape / view / permute、broadcast、contiguous |
| 3 | `03_autograd` | requires_grad、backward、叶子与非叶子 |
| 4 | `04_nn_module` | nn.Module、常用层、forward |
| 5 | `05_data_train` | Dataset / DataLoader、loss、optim、一步训练 |
| 6 | `06_checkpoint_eval` | state_dict、保存加载、train / eval |
| 7 | `07_cnn_seq` | 小 CNN + RNN / 序列基础 |
| 8 | `08_transformer_device` | 注意力 / Transformer 组件、device 迁移、常见调试坑 |
