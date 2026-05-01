import time
import serial
import sys
from datetime import datetime
import urllib.parse

# ================= 配置区域 (默认值) =================
import minimalmodbus
import random
import threading
import queue
import tkinter as tk
import configparser
import os
from tkinter import ttk, scrolledtext, messagebox
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import text

# ================= 配置区域 (默认值) =================
# 仿真模式开关 (True: 开启仿真，无需硬件; False: 连接真实PLC)
SIMULATION_MODE = False

# 数据库配置
# DB_HOST = '192.168.51.5' # 豪生扫码真实库[2026-02-09 21:23:11.831]
# --------正在校验条码数据 (基于数据库规则 + MES)...
DB_HOST = '127.0.0.1'
DB_PORT = '3306'
DB_NAME = 'haosheng'
DB_USER = 'admin2'
DB_PASS = 'QAZwsx123...' 
DB_URI = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"

# MES 数据库配置 (SQL Server)
HOSTNAME2 = '192.168.51.3'
PORT2 = '1433'
DATABASE2 = 'SMES_Production'
USERNAME2 = 'sa'
PASSWORD2 = 'Sa123456'
encoded_password2 = urllib.parse.quote_plus(PASSWORD2)
DB_URI2 = f"mssql+pymssql://{USERNAME2}:{encoded_password2}@{HOSTNAME2}:{PORT2}/{DATABASE2}?tds_version=7.0"

# 创建全局 MES 数据库引擎，使用连接池
# pool_size: 保持的连接数
# max_overflow: 当连接数用完时，允许额外创建的连接数
# pool_recycle: 连接回收时间（秒），防止连接被数据库断开
mes_engine = create_engine(DB_URI2, pool_size=10, max_overflow=20, pool_recycle=3600)

# 本地数据库引擎 (MySQL)
# 同样使用连接池，避免在 server_verify 中重复创建
local_engine = create_engine(DB_URI, pool_size=10, max_overflow=20, pool_recycle=3600)
LocalSession = sessionmaker(bind=local_engine)

# PLC 通讯配置默认值
DEFAULT_PLC_PORT = 'COM1'
DEFAULT_PLC_BAUDRATE = 9600
CONFIG_FILE = 'config.ini'

# ===========================================

# 数据库模型定义
Base = declarative_base()

class SysCodeRulesT(Base):
    __tablename__ = 'sys_coderules_t'

    id = Column(Integer, primary_key=True, autoincrement=True)
    person = Column(String(255), nullable=True, comment='人员')
    input11 = Column(String(255), nullable=True, comment='输入框11起始位')
    input12 = Column(String(255), nullable=True, comment='输入框12长度')
    input13 = Column(String(255), nullable=True, comment='输入框13内容')
    input21 = Column(String(255), nullable=True, comment='输入框21起始位')
    input22 = Column(String(255), nullable=True, comment='输入框22长度')
    input23 = Column(String(255), nullable=True, comment='输入框23内容')
    input31 = Column(String(255), nullable=True, comment='输入框31起始位')
    input32 = Column(String(255), nullable=True, comment='输入框32长度')
    input33 = Column(String(255), nullable=True, comment='输入框33内容')
    inputleng = Column(String(255), nullable=True, comment='字符长度')
    inputauto = Column(String(255), nullable=True, comment='串口端口')
    baud = Column(String(255), nullable=True, comment='波特率')
    inputff = Column(String(255), nullable=True, comment='非法字符')
    dropdown = Column(String(255), nullable=True, comment='下拉选项')
    condition1 = Column(Boolean, default=True, comment='条件1')
    condition2 = Column(Boolean, default=True, comment='条件2')
    condition3 = Column(Boolean, default=True, comment='条件3')
    useAutoMachine = Column(Boolean, default=False, comment='使用自动机')
    update_time = Column(DateTime, nullable=False, comment='修改时间')

    def __repr__(self):
        return f"<Rule(person='{self.person}', len={self.inputleng})>"

class SysQrcodeT(Base):
    __tablename__ = 'sys_qrcode_t'

    id = Column(Integer, primary_key=True, autoincrement=True)
    person = Column(String(255), comment='操作员')
    dept = Column(Integer, comment='部门ID')
    goods = Column(String(255), comment='产品名称/型号')
    qrcode = Column(String(255), comment='二维码')
    status = Column(String(50), comment='状态')
    error = Column(String(255), comment='错误信息')
    remark = Column(String(255), comment='备注')
    createTime = Column(DateTime, default=datetime.now, comment='创建时间')

# class SysUsersT(Base):
#     __tablename__ = 'sys_users_t'
#     id = Column(Integer, primary_key=True)
#     username = Column(String(255))
#     # dept = Column(Integer, nullable=True)


#  先当成所有都是最新的，不管是否打包的校验
# class SysPackAT(Base):
#     __tablename__ = 'sys_pack_a_t'
#     id = Column(Integer, primary_key=True)
#     agoods = Column(String(255))
#     astatus = Column(String(10))

# 全局变量：存储当前加载的规则
current_rule_config = None
def resource_path(relative_path):
    """ 打包时获取图片 """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)
def init_db_and_load_rule(person_name, log_func):
    """初始化数据库并加载当前人员的规则"""
    global current_rule_config
    log_func(f"正在连接数据库: {DB_HOST}...")
    session = None
    try:
        # 使用全局 LocalSession，避免重复创建 sessionmaker 类导致内存泄漏
        session = LocalSession()
        
        # 查询规则
        log_func(f"正在查询人员 '{person_name}' 的配置规则...")
        rule = session.query(SysCodeRulesT).filter_by(person=person_name).first()
        
        if rule:
            log_func("✅ 成功加载规则:")
            log_func(f"  - 字符长度限制: {rule.inputleng}")
            log_func(f"  - 非法字符: {rule.inputff}")
            log_func(f"  - 大小写管控: {rule.dropdown}")
            if rule.condition1:
                log_func(f"  - 规则1: 起始{rule.input11}, 长度{rule.input12}, 内容='{rule.input13}'")
            if rule.condition2:
                log_func(f"  - 规则2: 起始{rule.input21}, 长度{rule.input22}, 内容='{rule.input23}'")
            if rule.condition3:
                log_func(f"  - 规则3: 起始{rule.input31}, 长度{rule.input32}, 内容='{rule.input33}'")
            
            current_rule_config = rule
            return True
        else:
            log_func(f"❌ 未找到人员 '{person_name}' 的配置信息！请检查数据库或配置。")
            return False
            
    except Exception as e:
        log_func(f"❌ 数据库连接或查询失败: {e}")
        return False
    finally:
        if session:
            session.close()

class MockInstrument:
    """模拟 PLC 行为的类，用于无硬件测试"""
    def __init__(self, log_func, max_holes):
        self.log_func = log_func
        self.max_holes = max_holes
        self.registers = {
            541: 0x0000,  # D541: 穴号(低8), CCD(中4), 换盘信号(高4)
            542: 0x0000   # D542: 校验结果(低8), 单次握手(Bit14), 完成握手(Bit15)
        }
        self.scan_count = 0
        
    def read_register(self, registeraddress, number_of_decimals=0, functioncode=3, signed=False):
        val = self.registers.get(registeraddress, 0)
        
        # 模拟逻辑: 当读取 D541 时，自动更新模拟状态
        if registeraddress == 541:
            # 模拟: 每次读取，穴号 +1 (1~8)
            if self.scan_count >= self.max_holes:
                tray_signal = 0xF
                hole_no = 0 
            else:
                tray_signal = 0x0
                hole_no = self.scan_count + 1 
            
            val = (tray_signal << 12) | (0 << 8) | hole_no
            
        self.log_func(f"  [仿真PLC] 读取 D{registeraddress} -> 0x{val:04X}")
        return val

    def write_register(self, registeraddress, value, number_of_decimals=0, functioncode=16, signed=False):
        self.registers[registeraddress] = value
        self.log_func(f"  [仿真PLC] 写入 D{registeraddress} <- 0x{value:04X}")
        
        if registeraddress == 542:
            is_finish_signal = (value >> 15) & 1
            if is_finish_signal:
                self.log_func("  [仿真PLC] >> 收到完成信号，PLC准备换盘...")
                self.scan_count = 0 # 重置

def get_plc_instrument(port, slave_addr, timeout, log_func, max_holes_for_mock):
    """初始化并返回 PLC 通讯对象"""
    if SIMULATION_MODE:
        log_func("!!! 警告: 当前运行在仿真模式 (SIMULATION_MODE = True) !!!")
        return MockInstrument(log_func, max_holes_for_mock)

    try:
        inst = minimalmodbus.Instrument(port, slave_addr)
        inst.serial.baudrate = DEFAULT_PLC_BAUDRATE
        inst.serial.bytesize = 8
        inst.serial.parity = serial.PARITY_NONE
        inst.serial.stopbits = 1
        inst.serial.timeout = timeout
        inst.mode = minimalmodbus.MODE_RTU
        inst.clear_buffers_before_each_transaction = True
        return inst
    except Exception as e:
        log_func(f"初始化 PLC 连接失败: {e}")
        return None

def check_single_barcode(barcode, rule):
    """根据规则校验单个条码"""
    if not barcode:
        return False, "条码为空"
        
    # 1. 检查长度
    if rule.inputleng:
        try:
            expected_len = int(rule.inputleng)
            if len(barcode) != expected_len:
                return False, f"长度错误(实:{len(barcode)}/:{expected_len})"
        except ValueError:
            pass 

    # 2. 检查非法字符
    if rule.inputff:
        for char in rule.inputff:
            if char in barcode:
                return False, f"包含非法字符'{char}'"

    # 2.5 检查大小写
    if rule.dropdown == 'option1':
        if not barcode.isupper():
            return False, "必须全部为大写"
    elif rule.dropdown == 'option2':
        if not barcode.islower():
            return False, "必须全部为小写"

    # 3. 检查条件规则 1-3
    def check_sub_rule(start_str, len_str, content_str, rule_name):
        try:
            if not start_str or not len_str or not content_str:
                return True, ""
            start = int(start_str)
            length = int(len_str)
            py_start = start - 1
            if py_start < 0: py_start = 0
            sub_str = barcode[py_start : py_start + length]
            if sub_str != content_str:
                return False, f"{rule_name}不匹配(实:'{sub_str}'/期:'{content_str}')"
            return True, ""
        except Exception as e:
            return False, f"{rule_name}配置解析错误:{e}"

    if rule.condition1:
        ok, msg = check_sub_rule(rule.input11, rule.input12, rule.input13, "规则1")
        if not ok: return False, msg
        
    if rule.condition2:
        ok, msg = check_sub_rule(rule.input21, rule.input22, rule.input23, "规则2")
        if not ok: return False, msg

    if rule.condition3:
        ok, msg = check_sub_rule(rule.input31, rule.input32, rule.input33, "规则3")
        if not ok: return False, msg

    return True, "OK"

def searchsqlserver(qrcode, check_type):
    """
    传递二维码内容，查询mes里检验结果
    :param qrcode: 二维码
    :param check_type: mes里类型，1曲线；2防水
    """
    try: 
        
        sql = text("""
            SELECT TOP 1 result 
            FROM TBLCUSSNresult
            WHERE snno = :snno AND teststyle = :teststyle 
            ORDER BY eventtime DESC
        """)
        
        with mes_engine.connect() as conn:
            result = conn.execute(sql, {"snno": qrcode, "teststyle": check_type})
            row = result.fetchone()
            
            if not row:
                return {'data': 'NODATA'}, 200
            
            return {'data': row[0]}, 200
            
    except Exception as e:
        print(f"MES Query Error: {e}")
        # 出错时返回 ERROR，避免系统崩溃，记录日志在外部处理
        return {'data': 'ERROR', 'error': str(e)}, 500

 
def server_verify_act(session, barcode, user_name, use_curve, use_waterproof, goods, remark='scan_control', is_repair=False):
    """
    扫描验证逻辑
    :param session: 数据库会话
    :param barcode: 扫描的二维码
    :param user_name: 操作员名称
    :param use_curve: 是否曲线检验 (ismes)
    :param use_waterproof: 是否防水检验 (ismesfs)
    :param goods: 产品名称
    :param remark: 备注
    :param is_repair: 是否返修模式
    :return: (is_success, status_code, result_msg, db_object)
    """
    try:
        dt = datetime.now()
        
        # 1. 基础参数检查
        if not barcode or not goods:
            return False, "缺少参数", "缺少参数", None
            
        # 2. 获取用户和部门信息
        # TODO 部门信息
        # dept_user = session.query(SysUsersT).filter_by(username=user_name).first()
        dept_id = 1  # 默认部门 ID 1
        
        # 3. 如果是返修校验   先不管返修
        # if is_repair:
        #     existing_record = session.query(SysQrcodeT).filter_by(qrcode=barcode).first()
        #     if not existing_record:
        #         # 返修模式下无记录，返回 NODATA，不入库
        #         return True, "NODATA", "NODATA", None
            
        #     # 查询装托
        #     codes = session.query(SysPackAT).filter_by(agoods=barcode).first()
        #     if codes:
        #         return False, f"{codes.agoods}此条码已有装一阶记录！", "ERROR", None

        # 4. 初始化状态
        # l_status 默认为 OK
        status = 'OK'
        error = 'OK'
        
        # 5. MES 校验逻辑
        # (use_curve, use_waterproof) -> config
        status_config = {
            (True, True): {'type1': 1, 'type2': 2, 'err_prefix1': 'NG-1', 'err_msg1': '曲线NG', 
                           'err_prefix2': 'NG-2', 'err_msg2': '防水NG'},
            (True, False): {'type': 1, 'err_prefix': 'NG-1', 'err_msg': '曲线NG'},
            (False, True): {'type': 2, 'err_prefix': 'NG-2', 'err_msg': '防水NG'},
        }
        
        current_config = status_config.get((use_curve, use_waterproof))
        
        # 处理 MES 相关逻辑
        if current_config and status == 'OK':
            if use_curve and use_waterproof:
                # 双重检验
                res1, _ = searchsqlserver(barcode, current_config['type1'])
                data_result1 = res1.get('data')
                if data_result1 == 'NODATA':
                    status = 'NODATA'
                    error = 'NODATA'
                elif data_result1 != 'OK':
                    status = current_config['err_prefix1']
                    error = current_config['err_msg1']
                else:
                    # 第一项OK，查第二项
                    res2, _ = searchsqlserver(barcode, current_config['type2'])
                    data_result2 = res2.get('data')
                    if data_result2 == 'NODATA':
                        status = 'NODATA'
                        error = 'NODATA'
                    elif data_result2 != 'OK':
                        status = current_config['err_prefix2']
                        error = current_config['err_msg2']
                        
            elif use_curve or use_waterproof:
                # 单项检验
                check_type = current_config.get('type')
                res, _ = searchsqlserver(barcode, check_type)
                data_result = res.get('data')
                if data_result == 'NODATA':
                    status = 'NODATA'
                    error = 'NODATA'
                elif data_result != 'OK':
                    status = current_config['err_prefix']
                    error = current_config['err_msg']

        # 6. 检查重复刷码 (仅在非返修校验时进行)
        if not is_repair:
            # 原 Flask 逻辑：SysQrcodeT.query.filter_by(qrcode=qrcode, status=status).first()
            #  status=status，意味着如果当前判定为 NG-1，且库里已有 NG-1，则视为重复
            repeated_record = session.query(SysQrcodeT).filter_by(qrcode=barcode, status=status).first()
            if repeated_record:
                status = 'REPEATED'
                error = '重复'

        # # 7. 返修状态特殊处理 ，先不处理
        # if is_repair and status == 'NODATA':
        #     return True, "NODATA", "NODATA", None

        # 8. 构造插入记录
        new_data = SysQrcodeT(
            person=user_name,
            dept=dept_id,
            goods=goods,
            qrcode=barcode,
            status=status,
            error=error,
            # remark='scan_control',
            createTime=dt
        )
        # session.add(new_data)
        # session.commit()
        
        if status == 'OK':
            return True, "OK", status, new_data
        else:
            return False, f"{error}", status, new_data

    except Exception as e:
        return False, f"系统错误: {e}", "ERROR", None

def server_verify(tray_data, max_holes, log_func, person_name, use_curve, use_waterproof, goods_name):
    """真实的后台校验"""
    log_func("\n--------正在校验条码数据 (基于数据库规则 + MES)...")
    result_mask = 0
    
    # 建立数据库会话
    session = None
    try:
        # 使用全局 LocalSession，避免重复创建 sessionmaker 类导致内存泄漏
        session = LocalSession()
    except Exception as e:
        log_func(f"❌ 数据库连接失败: {e}")
        return 0
    
    try:
        if not current_rule_config:
            log_func("❌ 警告: 没有加载校验规则，所有条码判定为 NG")
            return 0
        
        batch_records = []

        # 遍历逻辑：按 1, 2, 3... (即扫描顺序) 取出数据进行校验
        for i in range(max_holes):
            logic_idx = i + 1  # 1, 2, 3... 代表第1个扫的，第2个扫的...
            data_obj = tray_data.get(logic_idx)
            
            barcode = None
            plc_hole_raw = "N/A"
            ccd_status_raw = "N/A"
            
            if data_obj:
                if isinstance(data_obj, dict):
                    barcode = data_obj.get('barcode')
                    plc_hole_raw = data_obj.get('plc_hole', 'N/A')
                    ccd_status_raw = data_obj.get('ccd_status', 'N/A')
                else:
                    barcode = data_obj
                    ccd_status_raw = "N/A"
            
            is_ok = False
            msg = "无条码"
            db_obj = None
            
            if barcode:
                # 0. 检查 CCD 状态 (15/0xF: OK, 其他: NG)
                 # 注意：ccd_status_raw 可能是 'N/A'，需要处理
                 is_ccd_ng = False
                 try:
                     if ccd_status_raw == 'N/A':
                        ccd_status_raw = "NG" # 如果不存在，默认NG
                        is_ccd_ng = True # 如果不存在，默认NG
                     elif int(ccd_status_raw) != 15: # 0xF = 15
                          is_ccd_ng = True
                 except:
                     is_ccd_ng = True # 发生异常也视为NG

                 if is_ccd_ng:
                      is_ok = False
                      msg = f"CCD检测NG({ccd_status_raw})"
                     # CCD NG 直接结束，不进行后续校验
                 else:
                    # 1. 基础规则校验 (长度、字符等)
                    is_rule_ok, rule_msg = check_single_barcode(barcode, current_rule_config)
                    
                    if not is_rule_ok:
                        msg = rule_msg
                        # 规则不通过， 直接返回NG
                    else:
                        # 2. 进阶业务校验 (server_verify_act)
                        # 修改为接收4个返回值，含 db_object
                        is_act_ok, act_msg, act_status, db_obj = server_verify_act(
                            session, barcode, person_name, use_curve, use_waterproof,goods_name
                        )
                        
                        if db_obj:
                            batch_records.append(db_obj)

                        if is_act_ok:
                            is_ok = True
                            msg = "OK"
                        else:
                            msg = f"{act_msg} ({act_status})"
            
            # 这里的 hole_idx 仅代表它是本盘中“第几个被扫到的”，不再强制对应 PLC 的具体穴号
            # 但为了日志显示一致性，我们显示“逻辑穴号 i+1”
            if is_ok:
                result_mask |= (1 << i)
                log_func(f"  逻辑穴号 {logic_idx} [PLC原值:{plc_hole_raw}, CCD:{ccd_status_raw}]: {barcode} -> OK")
            else:
                log_func(f"  逻辑穴号 {logic_idx} [PLC原值:{plc_hole_raw}, CCD:{ccd_status_raw}]: {barcode} -> NG ({msg})")
        
        # 批量插入
        if batch_records:
            try:
                session.add_all(batch_records)
                session.commit()
                log_func(f"  [DB] 批量插入 {len(batch_records)} 条记录成功")
            except Exception as e:
                session.rollback()
                log_func(f"❌ [DB] 批量插入失败: {e}")

    except Exception as e:
        log_func(f"❌ 校验过程发生异常: {e}")
    finally:
        if session:
            session.close()
            
    return result_mask

class ScanApp:
    def __init__(self, root):
        self.root = root
        self.root.title("扫码控制系统")
        self.root.geometry("800x600")

        try:
            self.root.iconbitmap(resource_path('p.ico'))
        except Exception as e:
            print(f"Set icon failed: {e}")
        # 变量
        self.var_person = tk.StringVar(value="admin")
        self.var_plc_addr = tk.IntVar(value=1)
        self.var_logic_delay = tk.DoubleVar(value=0.01)
        self.var_max_holes = tk.IntVar(value=4)
        self.var_reg_read = tk.IntVar(value=541)
        self.var_reg_write = tk.IntVar(value=542)
        self.var_barcode_input = tk.StringVar()
        
        # 新增检验选项
        self.var_check_curve = tk.BooleanVar(value=False)
        self.var_check_waterproof = tk.BooleanVar(value=False)
        self.var_goods = tk.StringVar(value="")
        
        # 线程控制
        self.is_running = False
        self.thread = None
        self.input_queue = queue.Queue()
        self.log_queue = queue.Queue(maxsize=1000) # 日志队列上线1000
        
        self.load_config()
        self.create_widgets()
        
        # 启动日志刷新定时器
        self.update_log_ui()

    def update_log_ui(self):
        """定时从队列读取日志并更新UI，避免阻塞主线程"""
        if not self.log_queue.empty():
            # Listbox 不需要 state='normal'，直接操作即可
            
            # 限制单次更新数量，防止大量日志瞬间卡死 UI
            msgs = []
            try:
                count = 0
                # 每次最多处理 100 条，剩余的留到下一次 100ms 后处理
                while count < 100:
                    msgs.append(self.log_queue.get_nowait())
                    count += 1
            except queue.Empty:
                pass
            
            if msgs:
                # 插入多行
                self.txt_log.insert(tk.END, *msgs)
                # 300 -200 +30  130
                # 限制日志行数
                MAX_LOG_LINES = 200
                current_lines = self.txt_log.size()
                if current_lines > MAX_LOG_LINES:
                    # 删除前N行 (Listbox delete 是包含两端的，所以减1)
                    num_to_delete = current_lines - 50
                    self.txt_log.delete(0, num_to_delete - 1)
                    
                self.txt_log.see(tk.END)


        # 每 100ms 刷新一次
        self.root.after(100, self.update_log_ui)

    def load_config(self):
        config = configparser.ConfigParser()
        if not os.path.exists(CONFIG_FILE):
            return

        try:
            config.read(CONFIG_FILE, encoding='utf-8')
            
            # [System]
            if 'System' in config:
                self.var_person.set(config['System'].get('person', 'admin'))
                self.var_logic_delay.set(config['System'].getfloat('logic_delay', 1.0))
                self.var_max_holes.set(config['System'].getint('max_holes', 2))
                self.var_goods.set(config['System'].get('var_goods', ''))
                
            # [PLC]
            if 'PLC' in config:
                self.var_plc_addr.set(config['PLC'].getint('station_id', 1))
                self.var_reg_read.set(config['PLC'].getint('reg_read', 541))
                self.var_reg_write.set(config['PLC'].getint('reg_write', 542))

                # 直接固定值，不从配置文件中读取，以后再说
                # global DEFAULT_PLC_PORT, DEFAULT_PLC_BAUDRATE
                # DEFAULT_PLC_PORT = config['PLC'].get('port', 'COM1')
                # DEFAULT_PLC_BAUDRATE = config['PLC'].getint('baudrate', 9600)
                
        except Exception as e:
            messagebox.showwarning("配置错误", f"加载配置文件失败: {e}\n将使用默认值。")

    def save_config(self):
        """保存当前配置到文件"""
        config = configparser.ConfigParser()
        if os.path.exists(CONFIG_FILE):
             config.read(CONFIG_FILE, encoding='utf-8')
        
        if 'System' not in config: config['System'] = {}
        config['System']['person'] = self.var_person.get()
        config['System']['logic_delay'] = str(self.var_logic_delay.get())
        config['System']['max_holes'] = str(self.var_max_holes.get())
        config['System']['var_goods'] = self.var_goods.get()
        
        if 'PLC' not in config: config['PLC'] = {}
        config['PLC']['station_id'] = str(self.var_plc_addr.get())
        config['PLC']['reg_read'] = str(self.var_reg_read.get())
        config['PLC']['reg_write'] = str(self.var_reg_write.get())
        # config['PLC']['port'] = DEFAULT_PLC_PORT
        # config['PLC']['baudrate'] = str(DEFAULT_PLC_BAUDRATE)
            
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                config.write(f)
        except Exception as e:
            self.log(f"配置保存失败: {e}")

    def create_widgets(self):
        # 1. 配置区域
        config_frame = ttk.LabelFrame(self.root, text="系统配置", padding=10)
        config_frame.pack(fill="x", padx=10, pady=5)
        
        grid_opts = {'padx': 5, 'pady': 5, 'sticky': 'w'}
        
        self.config_entries = []
        
        # Row 0
        ttk.Label(config_frame, text="操作人员:").grid(row=0, column=0, **grid_opts)
        e_person = ttk.Entry(config_frame, textvariable=self.var_person, width=15)
        e_person.grid(row=0, column=1, **grid_opts)
        self.config_entries.append(e_person)
        
        ttk.Label(config_frame, text="产品型号:").grid(row=0, column=2, **grid_opts)
        e_goods = ttk.Entry(config_frame, textvariable=self.var_goods, width=15)
        e_goods.grid(row=0, column=3, **grid_opts)
        self.config_entries.append(e_goods)
        
        ttk.Label(config_frame, text="PLC站号:").grid(row=0, column=4, **grid_opts)
        e_addr = ttk.Entry(config_frame, textvariable=self.var_plc_addr, width=10)
        e_addr.grid(row=0, column=5, **grid_opts)
        self.config_entries.append(e_addr)
        
        ttk.Label(config_frame, text="延迟(秒):").grid(row=0, column=6, **grid_opts)
        e_delay = ttk.Entry(config_frame, textvariable=self.var_logic_delay, width=10)
        e_delay.grid(row=0, column=7, **grid_opts)
        self.config_entries.append(e_delay)
        
        # Row 1
        ttk.Label(config_frame, text="最大穴数:").grid(row=1, column=0, **grid_opts)
        e_holes = ttk.Entry(config_frame, textvariable=self.var_max_holes, width=10)
        e_holes.grid(row=1, column=1, **grid_opts)
        self.config_entries.append(e_holes)
        
        ttk.Label(config_frame, text="读地址(D):").grid(row=1, column=2, **grid_opts)
        e_read = ttk.Entry(config_frame, textvariable=self.var_reg_read, width=10)
        e_read.grid(row=1, column=3, **grid_opts)
        self.config_entries.append(e_read)

        ttk.Label(config_frame, text="写地址(D):").grid(row=1, column=4, **grid_opts)
        e_write = ttk.Entry(config_frame, textvariable=self.var_reg_write, width=10)
        e_write.grid(row=1, column=5, **grid_opts)
        self.config_entries.append(e_write)
        
        # 新增 Checkbutton
        cb_curve = ttk.Checkbutton(config_frame, text="曲线检验", variable=self.var_check_curve)
        cb_curve.grid(row=1, column=6, **grid_opts)
        self.config_entries.append(cb_curve)
        
        cb_waterproof = ttk.Checkbutton(config_frame, text="防水检验", variable=self.var_check_waterproof)
        cb_waterproof.grid(row=1, column=7, **grid_opts)
        self.config_entries.append(cb_waterproof)
        
        # 2. 控制区域
        ctrl_frame = ttk.Frame(self.root, padding=5)
        ctrl_frame.pack(fill="x", padx=10)
        
        self.btn_start = ttk.Button(ctrl_frame, text="启动系统", command=self.start_system)
        self.btn_start.pack(side="left", padx=5)
        
        self.btn_stop = ttk.Button(ctrl_frame, text="停止系统", command=self.stop_system, state="disabled")
        self.btn_stop.pack(side="left", padx=5)
        
        # 3. 扫码输入区域
        input_frame = ttk.LabelFrame(self.root, text="扫码输入区 (请将光标置于此处)", padding=10)
        input_frame.pack(fill="x", padx=10, pady=5)
        
        self.entry_barcode = ttk.Entry(input_frame, textvariable=self.var_barcode_input, state='disabled')
        self.entry_barcode.pack(fill="x", padx=5)
        self.entry_barcode.bind('<Return>', self.on_barcode_enter)
        
        # 4. 日志区域
        log_frame = ttk.LabelFrame(self.root, text="运行日志", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # 使用 Listbox 替代 ScrolledText 以提升性能
        scrollbar = ttk.Scrollbar(log_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.txt_log = tk.Listbox(log_frame, font=("Consolas", 10), yscrollcommand=scrollbar.set)
        self.txt_log.pack(side=tk.LEFT, fill="both", expand=True)
        
        scrollbar.config(command=self.txt_log.yview)
        
    def log(self, msg):
        """完全禁用日志输出"""
        pass

    def on_barcode_enter(self, event):
        """处理扫码回车事件"""
        barcode = self.var_barcode_input.get().strip()
        if barcode:
            self.input_queue.put(barcode)
            self.var_barcode_input.set("") # 清空输入框
            # 保持焦点
            self.entry_barcode.focus_set()

    def set_config_state(self, state):
        for entry in self.config_entries:
            entry.config(state=state)

    def start_system(self):
        if self.is_running: return
        
        self.save_config()
        
        # 锁定配置
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.set_config_state("disabled")
        
        self.is_running = True
        self.thread = threading.Thread(target=self.worker_thread, daemon=True)
        self.thread.start()
        self.log(">>> 系统已启动 <<<")
        self.entry_barcode.config(state='normal')
        self.entry_barcode.focus_set()

    def stop_system(self):
        if not self.is_running: return
        self.is_running = False
        self.log(">>> 系统正在停止... <<<")
        # 发送一个空值打断可能的 input 等待
        self.input_queue.put(None)
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.entry_barcode.config(state='disabled')
        self.set_config_state("normal")

    # TODO  重构代码
    def worker_thread(self):
        """后台工作线程"""
        try:
            # 获取配置
            person = self.var_person.get()
            plc_addr = self.var_plc_addr.get()
            logic_delay = self.var_logic_delay.get()
            max_holes = self.var_max_holes.get()
            reg_read = self.var_reg_read.get()
            reg_write = self.var_reg_write.get()
            
            # 获取MES检验
            use_curve = self.var_check_curve.get()
            use_waterproof = self.var_check_waterproof.get()
            self.log(f"MES检验配置: 曲线检验={use_curve}, 防水检验={use_waterproof}")
            
            # 1. 初始化数据库
            if not init_db_and_load_rule(person, self.log):
                self.log("❌ 无法加载规则，系统启动中止！请检查人员名称或数据库连接。")
                self.root.after(0, self.stop_system)
                return
            
            # 2. 初始化 PLC (串口超时固定1秒)
            plc = get_plc_instrument(DEFAULT_PLC_PORT, plc_addr, 1.0, self.log, max_holes)
            if not plc:
                self.log("❌ PLC 初始化失败，线程退出。")
                self.root.after(0, self.stop_system)
                return

            current_tray_data = {}
            
            while self.is_running:
                try:
                    current_count = len(current_tray_data)
                    self.log(f"\n----------------------------------------")
                    self.log(f"当前盘进度: [{current_count}/{max_holes}]")
                    
                    # 阶段 1: 扫码
                    if current_count < max_holes:
                        # 允许输入
                        self.root.after(0, lambda: self.entry_barcode.config(state='normal'))
                        self.log(f"等待扫码 (第 {current_count+1} 个)...")
                        
                        # 等待队列输入
                        barcode = None
                        while self.is_running:
                            try:
                                barcode = self.input_queue.get(timeout=0.5)
                                break # 成功获取到数据
                            except queue.Empty:
                                continue # 超时，继续在内部等待，不刷新日志
                            
                        if barcode is None or not self.is_running: break
                        
                        self.log(f"-> 接收到条码: {barcode}")
                        
                        # 2. 读 PLC (读地址)
                        try:
                            d_read_val = plc.read_register(reg_read, 0)
                        except Exception as e:
                            self.log(f"PLC 读取失败: {e}")
                            continue
                        self.log(f"-> 读取PLC数据: {d_read_val:04X}")    
                        hole_no = d_read_val & 0xFF
                        # 新增：提取中4位作为 CCD 状态
                        ccd_val = (d_read_val >> 8) & 0xF
                        # 15 (0xF) 代表 OK，其他代表 NG
                        ccd_display = "OK" if ccd_val == 0xF else "NG"
                        self.log(f"-> PLC 反馈穴号: {hole_no}, CCD状态: {ccd_display}")
                        
                        # 检查穴号是否已存在
                        is_duplicate = False
                        for key, val in current_tray_data.items():
                            if val.get('plc_hole') == hole_no:
                                is_duplicate = True
                                break
                        
                        if is_duplicate:
                            self.log(f"!! 警告: 穴号 {hole_no} 已存在，跳过记录")
                            # 执行握手复位逻辑，防止PLC卡死
                            # 但不增加计数
                            BIT_SINGLE_HANDSHAKE = 14
                            try:
                                d_write_val = plc.read_register(reg_write, 0) # 读取一次
                                d_write_val |= (1 << BIT_SINGLE_HANDSHAKE) # 置位
                                plc.write_register(reg_write, d_write_val, 0) # 写入一次
                                d_read_val_1 = plc.read_register(reg_write, 0)  # 读取一次
                                self.log(f"-> (重复)单次写入: Bit 14 置 1 (当前值: {d_read_val_1:04X}) (保持 {logic_delay:.2f}s)")
                                
                                time.sleep(logic_delay)
                                d_write_val = plc.read_register(reg_write, 0)
                                d_write_val &= ~(1 << BIT_SINGLE_HANDSHAKE)
                                plc.write_register(reg_write, d_write_val, 0)
                                d_read_val_2 = plc.read_register(reg_write, 0)  # 读取一次
                                self.log(f"-> (重复)单次写入: Bit 14 置 0 (当前值: {d_read_val_2:04X})")
                            except Exception as e:
                                self.log(f"PLC 写入失败(重复逻辑): {e}")
                            
                            continue # 直接进入下一次循环，不执行后续正常的握手逻辑
                        else:
                            # 修改存储结构：使用扫描顺序作为 key，确保校验时按顺序取出
                            current_tray_data[current_count + 1] = {
                                'barcode': barcode,
                                'plc_hole': hole_no,
                                'ccd_status': ccd_val
                            }
                        
                        if SIMULATION_MODE and hasattr(plc, 'scan_count'):
                            plc.scan_count += 1

                        # 3. 握手逻辑 (写地址)
                        BIT_SINGLE_HANDSHAKE = 14
                        try:
                            d_write_val = plc.read_register(reg_write, 0)
                            d_write_val |= (1 << BIT_SINGLE_HANDSHAKE)
                            plc.write_register(reg_write, d_write_val, 0)
                            d_read_val_1 = plc.read_register(reg_write, 0)  # 读取一次
                            self.log(f"-> 单次写入: Bit 14 置 1 (当前值: {d_read_val_1:04X}) (保持 {logic_delay:.2f}s)")
                            
                            time.sleep(logic_delay)
                            
                            d_write_val = plc.read_register(reg_write, 0)
                            d_write_val &= ~(1 << BIT_SINGLE_HANDSHAKE)
                            plc.write_register(reg_write, d_write_val, 0)   
                            d_read_val_2 = plc.read_register(reg_write, 0)  # 读取一次
                            self.log(f"-> 单次写入: Bit 14 置 0 (当前值: {d_read_val_2:04X})")
                        except Exception as e:
                            self.log(f"PLC 写入失败: {e}")

                        continue

                    # 阶段 2: 盘满等待
                    # 禁止输入
                    self.root.after(0, lambda: self.entry_barcode.config(state='disabled'))
                    self.log("\n[系统] 当前盘已扫满，等待 PLC 换盘信号...")
                    while self.is_running:
                        try:
                            d_read_val = plc.read_register(reg_read, 0)
                            tray_signal = (d_read_val >> 12) & 0xF
                            if tray_signal == 0xF:
                                self.log("-> 检测到换盘信号 (0xF)")
                                # self.root.update_idletasks()   #等待的时候，重置一下ui，释放 缓存
                                break
                            time.sleep(0.1) # 增加微小延时，防止CPU占用过高
                        except Exception as e:
                            self.log(f"PLC 轮询错误: {e}")
                            time.sleep(1) # 出错时等待稍长
                    
                    if not self.is_running: break

                    # 阶段 3: 校验
                    goods_name = self.var_goods.get().strip() # 获取配置中的 goods
                    verify_result_mask = server_verify(
                        current_tray_data, 
                        max_holes, 
                        self.log, 
                        person, 
                        use_curve, 
                        use_waterproof,
                        goods_name
                    )
                    
                    # 阶段 4: 写入结果 (写地址)
                    BIT_BATCH_FINISH = 15
                    write_val = verify_result_mask | (1 << BIT_BATCH_FINISH)
                    try:
                        plc.write_register(reg_write, write_val, 0)
                        self.log(f"-> 写入结果 & 完成信号: 0x{write_val:04X}")
                    except Exception as e:
                        self.log(f"PLC 写入结果失败: {e}")

                    # 阶段 5: 等待复位
                    self.log("-> 等待 PLC 确认并复位换盘信号...")
                    while self.is_running:
                        try:
                            d_read_val = plc.read_register(reg_read, 0)
                            tray_signal = (d_read_val >> 12) & 0xF
                            if tray_signal == 0:
                                self.log("-> PLC 已复位换盘信号 (0x0)")
                                break
                            time.sleep(0.1) # 增加微小延时
                        except Exception as e:
                            self.log(f"PLC 等待复位错误: {e}")
                            time.sleep(1) # 出错时等待稍长
                            
                    if not self.is_running: break

                    # 复位完成信号
                    try:
                        d_write_val = plc.read_register(reg_write, 0)
                        d_write_val &= ~(1 << BIT_BATCH_FINISH)
                        plc.write_register(reg_write, d_write_val, 0)
                        self.log(f"-> 复位完成信号: Bit 15 置 0")
                    except Exception as e:
                        self.log(f"PLC 复位完成信号失败: {e}")

                    self.log("\n=== 本盘流程结束，准备下一盘 ===")
                    # self.root.update_idletasks()   #等待的时候，重置一下ui，释放 缓存
                    current_tray_data.clear()
                    if SIMULATION_MODE and hasattr(plc, 'scan_count'):
                        plc.scan_count = 0

                except Exception as e:
                    self.log(f"!! 循环发生未捕获错误: {e}")
                    time.sleep(2)

        except Exception as e:
            self.log(f"线程致命错误: {e}")
        finally:
            self.is_running = False
            self.root.after(0, lambda: self.btn_start.config(state="normal"))
            self.root.after(0, lambda: self.btn_stop.config(state="disabled"))
            self.log(">>> 线程已退出 <<<")

if __name__ == "__main__":
    root = tk.Tk()
    app = ScanApp(root)
    root.mainloop()
