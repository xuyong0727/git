# 扫码装箱项目 (CCD 自动机集成) 性能优化总结

**日期**: 2026年4月11日

## 问题现象
- **核心问题**: 现场程序 `scan_control.py` 在运行半小时后，Tkinter 界面中的输入框（扫码输入区）响应速度明显变慢，出现严重卡顿和延迟。
- **环境信息**: Python Tkinter 桌面程序，结合 SQLAlchemy 读写本地 MySQL 数据库与远程 MES 数据库 (SQL Server)。

## 诊断与分析

### 1. 排除数据库查询瓶颈
最初怀疑是本地 MySQL 数据库中 `sys_qrcode_t` 表的 `qrcode` 字段缺少索引，导致在扫码查重时 (`filter_by(qrcode=barcode, status=status)`) 发生全表扫描。
- **排查结果**: 客户确认本地数据库已建立组合索引，因此排除数据库查询拥塞拖慢后台线程的可能性。

### 2. 锁定 UI 主线程阻塞 (核心原因)
通过对比现场提供的两份代码 (`scan_control.py` 和阉割了日志输出的 `scan_control_nolog.py`)：
- `scan_control.py` 包含频繁的日志写入队列和 UI 刷新。
- `scan_control_nolog.py` 禁用了 `log()` 函数 (`pass`)，不刷新 UI 日志。
- **结论**: 运行 `scan_control.py` 时出现卡顿，而 `scan_control_nolog.py` 表现正常，证实了性能瓶颈**完全集中在 Tkinter UI 的日志刷新机制上**。

### 3. 具体性能消耗点剖析
1. **`tk.Listbox` 组件误用**: 
   - 原作者为提升性能将 `ScrolledText` 替换为了 `tk.Listbox`。
   - **问题所在**: `Listbox` 虽然初始化快，但在高频执行“头部删除 + 尾部插入”以维持行数限制时（当前逻辑为满 200 行删 150 行），在底层的 Tcl 解释器中会产生严重的内存碎片和高昂的重绘开销。这种瞬间的大量重绘操作几乎占满了 UI 主线程的时间片，导致输入框的 `<Return>` 回车事件和按键事件被严重积压，表现为输入延迟。
2. **Session 类工厂重复创建 (隐性消耗)**:
   - 在 `server_verify` 中每次校验都调用 `Session = sessionmaker(bind=local_engine)`。这会在 Python 内存中持续产生新的类定义，引发垃圾回收 (GC) 的频繁启动，进一步加剧了程序的间歇性卡顿。

## 优化方案计划 (待实施)
无需修改核心业务逻辑，仅需对 UI 和基础资源进行性能重构：

1. **重构日志 UI 组件**: 
   - 弃用 `tk.Listbox`，改回使用配置为 `state='disabled'` (只读) 的 `tk.Text` 组件。`tk.Text` 在处理长文本流的截断和追加时性能远高于 `Listbox` 的节点增删，且不会引发内存碎片。
2. **降低日志清理频率**: 
   - 调整日志截断逻辑的阈值。例如：当日志累积到 1000 行时，再通过 `text.delete('1.0', '500.0')` 批量清理前半部分，避免每隔几秒钟就进行高频 UI 抖动。
3. **修复 Session 泄漏**: 
   - 将 `Session = sessionmaker(bind=local_engine)` 提取为全局单例，每次校验时仅创建会话实例 `session = Session()`，避免持续产生无用的类定义。

实施上述三点优化后，可彻底解决输入框延迟问题，确保程序长效稳定运行。