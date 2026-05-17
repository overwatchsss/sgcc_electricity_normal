import logging
import os
import re
import time

import random
import base64
from datetime import datetime
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from sensor_updator import SensorUpdator
from error_watcher import ErrorWatcher
from typing import Optional

from const import *

from io import BytesIO
from PIL import Image
from captcha_solver.tencent import TencentCaptchaHandler
import platform
import numpy as np


class DataFetcher:

    def __init__(self, username: str, password: str):
        if 'PYTHON_IN_DOCKER' not in os.environ: 
            import dotenv
            dotenv.load_dotenv(verbose=True)
        self._username = username
        self._password = password

        self.tencent_captcha = TencentCaptchaHandler()

        self.DRIVER_IMPLICITY_WAIT_TIME = int(os.getenv("DRIVER_IMPLICITY_WAIT_TIME", 60))
        self.RETRY_TIMES_LIMIT = int(os.getenv("RETRY_TIMES_LIMIT", 5))
        self.LOGIN_EXPECTED_TIME = int(os.getenv("LOGIN_EXPECTED_TIME", 10))
        self.RETRY_WAIT_TIME_OFFSET_UNIT = int(os.getenv("RETRY_WAIT_TIME_OFFSET_UNIT", 10))
        self.IGNORE_USER_ID = os.getenv("IGNORE_USER_ID", "xxxxx,xxxxx").split(",")
        self.QR_CODE_LOGIN_WAIT_COUNT = int(os.getenv("QR_CODE_LOGIN_WAIT_COUNT", 7))
        self.QR_CODE_LOGIN_WAIT_TIME_INTERVAL_UNIT = int(os.getenv("QR_CODE_LOGIN_WAIT_TIME_INTERVAL_UNIT", 10))
        # 本地运行用更短的步骤等待
        self._step_wait = 2 if 'PYTHON_IN_DOCKER' not in os.environ else self.RETRY_WAIT_TIME_OFFSET_UNIT
        logging.info(f"DataFetcher 初始化完成: 用户={username}, 步骤等待={self._step_wait}s, "
                     f"隐式等待={self.DRIVER_IMPLICITY_WAIT_TIME}s, 重试次数={self.RETRY_TIMES_LIMIT}")
        self._init_db()
    
    def _init_db(self):
        self.db_type = os.getenv("DB_TYPE", "None").lower()
        if self.db_type == 'mysql':
            from db import MysqlDB
            self.db = MysqlDB()
            logging.info("Using MySQL database to store data.")
        elif self.db_type == 'sqlite':
            from db import SqliteDB
            self.db = SqliteDB()
            logging.info("Using Sqlite database to store data.")
        else:
            self.db = None
            logging.info("No database will be used to store data.")

    # @staticmethod
    def _click_button(self, driver, button_search_type, button_search_key):
        '''wrapped click function, click only when the element is clickable'''
        click_element = driver.find_element(button_search_type, button_search_key)
        # logging.info(f"click_element:{button_search_key}.is_displayed() = {click_element.is_displayed()}\r")
        # logging.info(f"click_element:{button_search_key}.is_enabled() = {click_element.is_enabled()}\r")
        WebDriverWait(driver, self.DRIVER_IMPLICITY_WAIT_TIME).until(EC.element_to_be_clickable(click_element))
        driver.execute_script("arguments[0].click();", click_element)

    def _wait_for_post_login_state(self, driver, timeout=12) -> str:
        """Wait after password submit and return the detected state."""
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.current_url != LOGIN_URL
                or self.tencent_captcha.has_captcha(d)
                or bool(self._get_error_message(d, "//div[@class='errmsg-tip']//span"))
            )
        except Exception:
            pass

        if driver.current_url != LOGIN_URL:
            return "success"
        if self.tencent_captcha.has_captcha(driver):
            return "captcha"
        if self._get_error_message(driver, "//div[@class='errmsg-tip']//span"):
            return "error"
        return "unknown"

    def insert_expand_data(self, data:dict):
        self.db.insert_expand_data(data)
                
    def _get_webdriver(self):
        logging.info(f"正在初始化 WebDriver, 平台: {platform.system()}")
        if platform.system() == 'Windows':
            from selenium.webdriver.edge.options import Options as EdgeOptions
            edge_options = EdgeOptions()
            edge_options.add_argument("--start-maximized")
            edge_options.add_argument("--disable-blink-features=AutomationControlled")
            edge_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            edge_options.add_experimental_option("useAutomationExtension", False)
            edge_options.add_argument(
                "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0")
            logging.info("使用 Edge 浏览器 (Windows 模式)")
            driver = webdriver.Edge(
                service=EdgeService(EdgeChromiumDriverManager(
                    url="https://msedgedriver.microsoft.com/",
                    latest_release_url="https://msedgedriver.microsoft.com/LATEST_RELEASE"
                ).install()),
                options=edge_options
            )
            driver.implicitly_wait(self.DRIVER_IMPLICITY_WAIT_TIME)
        else:
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--start-maximized")

            # --- 规避反爬 ---
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option("useAutomationExtension", False)
            chrome_options.add_argument(
                "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

            # 指定 chromium 和 chromedriver 的路径
            if 'PYTHON_IN_DOCKER' in os.environ:
                chrome_options.binary_location = "/usr/bin/chromium"
                service = ChromeService(executable_path="/usr/bin/chromedriver")
                logging.info("使用 Chromium 浏览器 (Docker 模式)")
            else:
                service = ChromeService()
                logging.info("使用 Chrome 浏览器 (Linux 桌面模式)")

            driver = webdriver.Chrome(
                options=chrome_options,
                service=service,
            )
            driver.implicitly_wait(self.DRIVER_IMPLICITY_WAIT_TIME)
        logging.info("WebDriver 初始化完成")
        return driver

    @ErrorWatcher.watch
    def _login(self, driver, phone_code = False):
        logging.info(f"开始登录流程, 账号: {self._username}, 手机验证码模式: {phone_code}")
        try:
            driver.get(LOGIN_URL)
            WebDriverWait(driver, self.DRIVER_IMPLICITY_WAIT_TIME * 3).until(EC.visibility_of_element_located((By.CLASS_NAME, "user")))
        except:
            logging.debug(f"Login failed, open URL: {LOGIN_URL} failed.")
        logging.info(f"已打开登录页面: {LOGIN_URL}")
        time.sleep(self._step_wait * 2)
        # swtich to username-password login page
        # 临时关闭隐式等待，避免与 WebDriverWait 叠加导致超时
        driver.implicitly_wait(0)
        try:
            WebDriverWait(driver, 10).until(
                EC.invisibility_of_element_located((By.CLASS_NAME, 'el-loading-mask')))
        finally:
            driver.implicitly_wait(self.DRIVER_IMPLICITY_WAIT_TIME)  # 恢复隐式等待

        element = WebDriverWait(driver, self.DRIVER_IMPLICITY_WAIT_TIME).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'user')))
        driver.execute_script("arguments[0].click();", element)
        logging.info("点击「账号密码登录」切换")
        self._click_button(driver, By.XPATH, '//*[@id="login_box"]/div[1]/div[1]/div[2]/span')
        time.sleep(self._step_wait)
        # click agree button
        self._click_button(driver, By.XPATH, '//*[@id="login_box"]/div[2]/div[1]/form/div[1]/div[3]/div/span[2]')
        logging.info("已勾选「同意」协议")
        time.sleep(self._step_wait)
        if phone_code:
            self._click_button(driver, By.XPATH, '//*[@id="login_box"]/div[1]/div[1]/div[3]/span')
            input_elements = driver.find_elements(By.CLASS_NAME, "el-input__inner")
            input_elements[2].send_keys(self._username)
            logging.info(f"input_elements username : {self._username}\r")
            self._click_button(driver, By.XPATH, '//*[@id="login_box"]/div[2]/div[2]/form/div[1]/div[2]/div[2]/div/a')
            code = input("Input your phone verification code: ")
            input_elements[3].send_keys(code)
            logging.info(f"input_elements verification code: {code}.\r")
            # click login button
            self._click_button(driver, By.XPATH, '//*[@id="login_box"]/div[2]/div[2]/form/div[2]/div/button/span')
            time.sleep(self._step_wait * 2)
            logging.info("Click login button.\r")

            return True
        # 增加判空校验便于测试fallback
        elif self._password is not None and len(self._password) > 0:
            # input username and password
            input_elements = driver.find_elements(By.CLASS_NAME, "el-input__inner")
            input_elements[0].send_keys(self._username)
            input_elements[1].send_keys(self._password)
            logging.info(f"已输入账号密码, 账号: {self._username}")

            for login_attempt in range(1, self.RETRY_TIMES_LIMIT + 1):
                # click login button
                self._click_button(driver, By.CLASS_NAME, "el-button.el-button--primary")
                time.sleep(self._step_wait * 2)
                logging.info(f"已点击登录按钮 (第 {login_attempt}/{self.RETRY_TIMES_LIMIT} 次)")

                # Wait for post-login state: success, captcha, or error
                post_login_state = self._wait_for_post_login_state(driver)
                logging.info(f"登录后页面状态: {post_login_state}")

                if post_login_state == "success":
                    logging.info("密码登录成功!")
                    return True

                if post_login_state == "captcha":
                    captcha_info = self.tencent_captcha.get_info(driver)
                    logging.info(
                        f"检测到验证码: 类型={captcha_info.get('mode')}, 提示文字={captcha_info.get('prompt', '')}"
                    )
                    if captcha_info.get("mode") == "point_click":
                        for retry_times in range(1, self.RETRY_TIMES_LIMIT + 1):
                            logging.info(f"开始第 {retry_times} 次点选验证码识别...")
                            if self.tencent_captcha.solve_point_click_captcha(driver, self.DRIVER_IMPLICITY_WAIT_TIME):
                                time.sleep(self._step_wait)
                                if driver.current_url != LOGIN_URL:
                                    logging.info("点选验证码识别成功, 已通过验证!")
                                    return True
                            logging.info(f"第 {retry_times} 次点选验证码识别失败, 正在刷新验证码...")
                            self.tencent_captcha._click_point_click_refresh(driver)
                            time.sleep(self._step_wait)

                    logging.error("验证码识别多次失败, 尝试备选登录方案")
                    return self._fallback_login(driver)
                elif post_login_state == "error":
                    error = self._get_error_message(driver, "//div[@class='errmsg-tip']//span")
                    logging.info(f"登录错误信息: {error}")
                    # RK001 (网络连接超时) or similar transient errors: retry
                    if "RK001" in (error or "") or "超时" in (error or "") or "重试" in (error or ""):
                        logging.info(f"检测到临时错误 [{error}], 正在重新输入账号密码重试 ({login_attempt}/{self.RETRY_TIMES_LIMIT})...")
                        try:
                            input_elements = driver.find_elements(By.CLASS_NAME, "el-input__inner")
                            input_elements[0].clear()
                            input_elements[0].send_keys(self._username)
                            input_elements[1].clear()
                            input_elements[1].send_keys(self._password)
                        except Exception:
                            pass
                        time.sleep(self._step_wait)
                        continue

            return self._fallback_login(driver)

    def _get_error_message(self, driver, path) -> Optional[str]:
        """获取错误信息，如果不存在则返回 None"""
        # 关闭隐式等待
        driver.implicitly_wait(0)
        try:
            element = driver.find_element(By.XPATH, path)
            return element.text
        except Exception:
            return None
        finally:
            driver.implicitly_wait(self.DRIVER_IMPLICITY_WAIT_TIME)  # 恢复隐式等待

    def _fallback_login(self, driver) -> bool:
        """使用 fallback 登录"""
        fallback = os.getenv("LOGIN_FALLBACK")
        if fallback == 'qrcode':
            return self._qr_login(driver)
        return False

    def _qr_login(self, driver) -> bool:
        logging.info("密码登录失败, 切换到二维码登录模式")
        # 切换验证码
        element = WebDriverWait(driver, self.DRIVER_IMPLICITY_WAIT_TIME).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'qr_code')))
        driver.execute_script("arguments[0].click();", element)
        logging.info("已切换到二维码登录模式")

        time.sleep(self._step_wait)
        # 获取登录二维码
        qrElement = WebDriverWait(driver, self.DRIVER_IMPLICITY_WAIT_TIME).until(
            EC.visibility_of_element_located((By.XPATH, "//div[@class='sweepCodePic']//img")))
        logging.info("找到二维码图片元素")
        img_src = qrElement.get_attribute('src')

        if img_src.startswith('data:image'):
            base64_data = img_src.split(',')[1]
            img_screenshot = base64.b64decode(base64_data)
        else:
          logging.info('二维码图片非 base64 格式, 使用截图方式获取')
          img_screenshot = qrElement.screenshot_as_png

        from const import get_data_dir
        qr_path = os.path.join(get_data_dir(), 'login_qr_code.png')
        with open(qr_path, "wb") as f:
            f.write(img_screenshot)
            logging.info(f"二维码已保存到 {qr_path}, 请扫描登录")

        from notify import UrlLoginQrCodeNotify
        notifyFunc = UrlLoginQrCodeNotify()
        notifyFunc(img_screenshot)
        logging.info(f"等待扫码登录, 最长等待 {self.QR_CODE_LOGIN_WAIT_COUNT * self.QR_CODE_LOGIN_WAIT_TIME_INTERVAL_UNIT} 秒...")
        for i in range(1, self.QR_CODE_LOGIN_WAIT_COUNT + 1):
            logging.info(f'等待扫码... [{i}/{self.QR_CODE_LOGIN_WAIT_COUNT}] (每 {self.QR_CODE_LOGIN_WAIT_TIME_INTERVAL_UNIT}s 检查一次)')
            time.sleep(self.QR_CODE_LOGIN_WAIT_TIME_INTERVAL_UNIT)
            if (driver.current_url != LOGIN_URL):
                logging.info("扫码登录成功!")
                return True
            else:
                error = self._get_error_message(driver, "//div[@class='sweepCodePic']//div[@class='erwBg']//p")
                if error is not None:
                    logging.error(f'二维码登录失败: {error}')
                    return False

        logging.warning("扫码登录超时, 未在规定时间内完成扫码")

        return False
        
    def fetch(self):

        """main logic here"""

        driver = self._get_webdriver()
        ErrorWatcher.instance().set_driver(driver)
        
        driver.maximize_window() 
        time.sleep(self._step_wait)
        logging.info("Webdriver initialized.")
        updator = SensorUpdator()
        
        try:
            if os.getenv("DEBUG_MODE", "false").lower() == "true":
                if self._login(driver,phone_code=True):
                    logging.info("login successed !")
                else:
                    logging.info("login unsuccessed !")
                    raise Exception("login unsuccessed")
            else:
                if self._login(driver):
                    logging.info("login successed !")
                else:
                    logging.info("login unsuccessed !")
                    raise Exception("login unsuccessed")
        except Exception as e:
            logging.error(
                f"Webdriver quit abnormly, reason: {e}. {self.RETRY_TIMES_LIMIT} retry times left.")
            driver.quit()
            return

        logging.info(f"登录成功! 当前页面: {LOGIN_URL}")
        time.sleep(self._step_wait)
        logging.info("正在获取用户 ID 列表...")
        user_id_list = self._get_user_ids(driver)
        if not user_id_list:
            logging.error("获取用户 ID 列表失败")
            driver.quit()
            return
        logging.info(f"共获取到 {len(user_id_list)} 个用户: {user_id_list}, 其中 {self.IGNORE_USER_ID} 将被忽略")
        time.sleep(self._step_wait)


        for userid_index, user_id in enumerate(user_id_list):           
            logging.info(f"===== 开始处理第 {userid_index + 1}/{len(user_id_list)} 个用户: {user_id} =====")
            try: 
                # switch to electricity charge balance page
                driver.get(BALANCE_URL) 
                time.sleep(self._step_wait)
                logging.info(f"正在切换到用户 [{user_id}]...")
                self._choose_current_userid(driver,userid_index)
                time.sleep(self._step_wait)
                current_userid = self._get_current_userid(driver)
                if current_userid in self.IGNORE_USER_ID:
                    logging.info(f"用户 {current_userid} 在忽略列表中, 跳过")
                    continue
                else:
                    logging.info(f"当前用户: {current_userid}, 开始获取用电数据...")
                    ### get data 
                    balance, last_daily_date, last_daily_usage, yearly_charge, yearly_usage, month_charge, month_usage  = self._get_all_data(driver, user_id, userid_index)
                    logging.info(f"用户 [{user_id}] 数据获取完成: 余额={balance}CNY, 最近日用电={last_daily_usage}kWh({last_daily_date}), "
                                 f"年度用电={yearly_usage}kWh, 年度电费={yearly_charge}CNY, 月用电={month_usage}kWh, 月电费={month_charge}CNY")
                    updator.update_one_userid(user_id, balance, last_daily_date, last_daily_usage, yearly_charge, yearly_usage, month_charge, month_usage)
        
                    time.sleep(self._step_wait)
            except Exception as e:
                if (userid_index != len(user_id_list)):
                    logging.info(f"用户 {user_id} 数据获取失败: {e}, 继续处理下一个用户")
                else:
                    logging.info(f"用户 {user_id} 数据获取失败: {e}")
                    logging.info("Webdriver quit after fetching data successfully.")
                continue

        logging.info("所有用户数据处理完成, 关闭浏览器")
        driver.quit()


    def _get_current_userid(self, driver):
        current_userid = driver.find_element(By.XPATH, '//*[@id="app"]/div/div/article/div/div/div[2]/div/div/div[1]/div[2]/div/div/div/div[2]/div/div[1]/div/ul/div/li[1]/span[2]').text
        return current_userid
    
    def _choose_current_userid(self, driver, userid_index):
        elements = driver.find_elements(By.CLASS_NAME, "button_confirm")
        if elements:
            self._click_button(driver, By.XPATH, f'''//*[@id="app"]/div/div[2]/div/div/div/div[2]/div[2]/div/button''')
        time.sleep(self._step_wait)
        self._click_button(driver, By.CLASS_NAME, "el-input__suffix")
        time.sleep(self._step_wait)
        self._click_button(driver, By.XPATH, f"/html/body/div[2]/div[1]/div[1]/ul/li[{userid_index+1}]/span")
        

    def _get_all_data(self, driver, user_id, userid_index):
        logging.info(f"[{user_id}] 正在获取电费余额...")
        balance = self._get_electric_balance(driver)
        if (balance is None):
            logging.error(f"[{user_id}] 获取电费余额失败")
        else:
            logging.info(f"[{user_id}] 电费余额: {balance} 元")

        # swithc to electricity usage page
        logging.info(f"[{user_id}] 正在切换到用电量页面...")
        driver.get(ELECTRIC_USAGE_URL)
        time.sleep(self._step_wait)
        self._choose_current_userid(driver, userid_index)
        time.sleep(self._step_wait)

        # get data for each user id
        logging.info(f"[{user_id}] 正在获取年度用电数据...")
        yearly_usage, yearly_charge = self._get_yearly_data(driver)

        if yearly_usage is None:
            logging.error(f"[{user_id}] 获取年度用电量失败")
        else:
            logging.info(f"[{user_id}] 年度用电量: {yearly_usage} kWh")
        if yearly_charge is None:
            logging.error(f"[{user_id}] 获取年度电费失败")
        else:
            logging.info(f"[{user_id}] 年度电费: {yearly_charge} 元")

        # 按月获取数据
        logging.info(f"[{user_id}] 正在获取月度用电数据...")
        month, month_usage, month_charge = self._get_month_usage(driver)
        if month is None:
            logging.error(f"[{user_id}] 获取月度用电数据失败")
        else:
            for m in range(len(month)):
                logging.info(f"[{user_id}] {month[m]}: 用电 {month_usage[m]} kWh, 电费 {month_charge[m]} 元")

        # get yesterday usage
        logging.info(f"[{user_id}] 正在获取每日用电量...")
        last_daily_date, last_daily_usage = self._get_yesterday_usage(driver)
        if last_daily_usage is None:
            logging.error(f"[{user_id}] 获取每日用电量失败")
        else:
            logging.info(f"[{user_id}] 最近用电: {last_daily_date} 用电 {last_daily_usage} kWh")
        if month is None:
            logging.error(f"Get month power usage for {user_id} failed, pass")

        # 新增储存用电量
        if self.db is not None:
            # 将数据存储到数据库
            logging.info(f"[{user_id}] 数据库类型: {self.db_type}, 开始保存数据到数据库")
            # 按天获取数据 7天/30天
            date, usages = self._get_daily_usage_data(driver)
            self._save_user_data(user_id, balance, last_daily_date, last_daily_usage, date, usages, month, month_usage, month_charge, yearly_charge, yearly_usage)
        else:
            logging.info(f"[{user_id}] 未配置数据库, 跳过数据存储")

        
        if month_charge:
            month_charge = month_charge[-1]
        else:
            month_charge = None
        if month_usage:
            month_usage = month_usage[-1]
        else:
            month_usage = None

        return balance, last_daily_date, last_daily_usage, yearly_charge, yearly_usage, month_charge, month_usage

    def _get_user_ids(self, driver):
        try:
            # 刷新网页
            driver.refresh()
            time.sleep(self._step_wait * 2)
            element = WebDriverWait(driver, self.DRIVER_IMPLICITY_WAIT_TIME).until(EC.presence_of_element_located((By.CLASS_NAME, 'el-dropdown')))
            # click roll down button for user id
            self._click_button(driver, By.XPATH, "//div[@class='el-dropdown']/span")
            logging.debug(f'''self._click_button(driver, By.XPATH, "//div[@class='el-dropdown']/span")''')
            time.sleep(self._step_wait)
            # wait for roll down menu displayed
            target = driver.find_element(By.CLASS_NAME, "el-dropdown-menu.el-popper").find_element(By.TAG_NAME, "li")
            logging.debug(f'''target = driver.find_element(By.CLASS_NAME, "el-dropdown-menu.el-popper").find_element(By.TAG_NAME, "li")''')
            time.sleep(self._step_wait)
            WebDriverWait(driver, self.DRIVER_IMPLICITY_WAIT_TIME).until(EC.visibility_of(target))
            time.sleep(self._step_wait)
            logging.debug(f'''WebDriverWait(driver, self.DRIVER_IMPLICITY_WAIT_TIME).until(EC.visibility_of(target))''')
            WebDriverWait(driver, self.DRIVER_IMPLICITY_WAIT_TIME).until(
                EC.text_to_be_present_in_element((By.XPATH, "//ul[@class='el-dropdown-menu el-popper']/li"), ":"))
            time.sleep(self._step_wait)

            # get user id one by one
            userid_elements = driver.find_element(By.CLASS_NAME, "el-dropdown-menu.el-popper").find_elements(By.TAG_NAME, "li")
            userid_list = []
            for element in userid_elements:
                userid_list.append(re.findall("[0-9]+", element.text)[-1])
            return userid_list
        except Exception as e:
            logging.error(
                f"Webdriver quit abnormly, reason: {e}. get user_id list failed.")
            return []

    def _get_electric_balance(self, driver):
        try:
            try:
                # 定位是否有"应交金额"标题（确认是后缴费账户）
                title_text = driver.find_element(By.XPATH, "//p[contains(@class, 'balance_title') and contains(text(), '应交金额')]").text
                if "应交金额" in title_text:
                    # 后缴费账户：需要查找"账户余额"，而不是"应交金额"
                    # 查找包含"账户余额"的balance_title元素，然后获取其内部的金额
                    balance_content = driver.find_element(By.XPATH, "//p[contains(@class, 'balance_title') and contains(text(), '账户余额')]")
                    # 提取数字部分
                    balance_text = re.sub(r'[^\d.]', '', balance_content.text)
                    if balance_text:
                        return float(balance_text)
            except Exception as e:
                # 后缴费账户解析失败，继续尝试预缴费账户逻辑
                pass

            # 2. 预缴费账户的"账户余额"（原逻辑）
            balance_text = driver.find_element(By.CLASS_NAME, "cff8").text
            balance = balance_text.replace("元", "")
            if "欠费" in balance_text:
                return -float(balance)
            else:
                return float(balance)
        except Exception as e:
            logging.error(f"Failed to get balance: {e}")
            return None

    def _get_yearly_data(self, driver):

        try:
            if datetime.now().month == 1:
                self._click_button(driver, By.XPATH, '//*[@id="pane-first"]/div[1]/div/div[1]/div/div/input')
                time.sleep(self._step_wait)
                span_element = driver.find_element(By.XPATH, f"//span[text() = '{datetime.now().year - 1}']")
                span_element.click()
                time.sleep(self._step_wait)
            self._click_button(driver, By.XPATH, "//div[@class='el-tabs__nav is-top']/div[@id='tab-first']")
            time.sleep(self._step_wait)
            # wait for data displayed
            target = driver.find_element(By.CLASS_NAME, "total")
            WebDriverWait(driver, self.DRIVER_IMPLICITY_WAIT_TIME).until(EC.visibility_of(target))
        except Exception as e:
            logging.error(f"The yearly data get failed : {e}")
            return None, None

        # get data
        try:
            yearly_usage = driver.find_element(By.XPATH, "//ul[@class='total']/li[1]/span").text
        except Exception as e:
            logging.error(f"The yearly_usage data get failed : {e}")
            yearly_usage = None

        try:
            yearly_charge = driver.find_element(By.XPATH, "//ul[@class='total']/li[2]/span").text
        except Exception as e:
            logging.error(f"The yearly_charge data get failed : {e}")
            yearly_charge = None

        return yearly_usage, yearly_charge

    def _get_yesterday_usage(self, driver):
        """获取最近一次用电量"""
        try:
            # 点击日用电量
            self._click_button(driver, By.XPATH, "//div[@class='el-tabs__nav is-top']/div[@id='tab-second']")
            time.sleep(self._step_wait)
            # wait for data displayed
            usage_element = driver.find_element(By.XPATH,
                                                "//div[@class='el-tab-pane dayd']//div[@class='el-table__body-wrapper is-scrolling-none']/table/tbody/tr[1]/td[2]/div")
            WebDriverWait(driver, self.DRIVER_IMPLICITY_WAIT_TIME).until(EC.visibility_of(usage_element)) # 等待用电量出现

            # 增加是哪一天
            date_element = driver.find_element(By.XPATH,
                                                "//div[@class='el-tab-pane dayd']//div[@class='el-table__body-wrapper is-scrolling-none']/table/tbody/tr[1]/td[1]/div")
            last_daily_date = date_element.text # 获取最近一次用电量的日期
            return last_daily_date, float(usage_element.text)
        except Exception as e:
            logging.error(f"The yesterday data get failed : {e}")
            return None, None

    def _get_month_usage(self, driver):
        """获取每月用电量"""

        try:
            self._click_button(driver, By.XPATH, "//div[@class='el-tabs__nav is-top']/div[@id='tab-first']")
            time.sleep(self._step_wait)
            if datetime.now().month == 1:
                self._click_button(driver, By.XPATH, '//*[@id="pane-first"]/div[1]/div/div[1]/div/div/input')
                time.sleep(self._step_wait)
                span_element = driver.find_element(By.XPATH, f"//span[text() = '{datetime.now().year - 1}']")
                span_element.click()
                time.sleep(self._step_wait)
            # wait for month displayed
            target = driver.find_element(By.CLASS_NAME, "total")
            WebDriverWait(driver, self.DRIVER_IMPLICITY_WAIT_TIME).until(EC.visibility_of(target))
            month_element = driver.find_element(By.XPATH, "//*[@id='pane-first']/div[1]/div[2]/div[2]/div/div[3]/table/tbody").text
            month_element = month_element.split("\n")
            month_element = [x for x in month_element if x != "MAX"]
            if len(month_element) % 3 != 0:
                month_element = month_element[:-(len(month_element) % 3)]
            month_element = np.array(month_element).reshape(-1, 3)
            # 将每月的用电量保存为List
            month = []
            usage = []
            charge = []
            for i in range(len(month_element)):
                month.append(month_element[i][0])
                usage.append(month_element[i][1])
                charge.append(month_element[i][2])
            return month, usage, charge
        except Exception as e:
            logging.error(f"The month data get failed : {e}")
            return None,None,None

    # 增加获取每日用电量的函数
    def _get_daily_usage_data(self, driver):
        """储存指定天数的用电量"""
        retention_days = int(os.getenv("DATA_RETENTION_DAYS", 7))  # 默认值为7天
        logging.info(f"正在获取每日用电量数据 (保留 {retention_days} 天)")
        self._click_button(driver, By.XPATH, "//div[@class='el-tabs__nav is-top']/div[@id='tab-second']")
        time.sleep(self._step_wait)

        # 7 天在第一个 label, 30 天 开通了智能缴费之后才会出现在第二个, (sb sgcc)
        if retention_days == 7:
            self._click_button(driver, By.XPATH, "//*[@id='pane-second']/div[1]/div/label[1]/span[1]")
        elif retention_days == 30:
            self._click_button(driver, By.XPATH, "//*[@id='pane-second']/div[1]/div/label[2]/span[1]")
        else:
            logging.error(f"Unsupported retention days value: {retention_days}")
            return

        time.sleep(self._step_wait)

        # 等待用电量的数据出现
        usage_element = driver.find_element(By.XPATH,
                                            "//div[@class='el-tab-pane dayd']//div[@class='el-table__body-wrapper is-scrolling-none']/table/tbody/tr[1]/td[2]/div")
        WebDriverWait(driver, self.DRIVER_IMPLICITY_WAIT_TIME).until(EC.visibility_of(usage_element))

        # 获取用电量的数据
        days_element = driver.find_elements(By.XPATH,
                                            "//*[@id='pane-second']/div[2]/div[2]/div[1]/div[3]/table/tbody/tr")  # 用电量值列表
        date = []
        usages = []
        # 将用电量保存为字典
        for i in days_element:
            day = i.find_element(By.XPATH, "td[1]/div").text
            usage = i.find_element(By.XPATH, "td[2]/div").text
            if usage != "":
                usages.append(usage)
                date.append(day)
            else:
                logging.info(f"日期 {day} 的用电量为空, 跳过")
        logging.info(f"成功获取 {len(date)} 天的每日用电量数据")
        return date, usages

    def _save_user_data(self, user_id, balance, last_daily_date, last_daily_usage, date, usages, month, month_usage, month_charge, yearly_charge, yearly_usage):
        # 连接数据库集合
        if self.db.connect_user_db(user_id):
            # 写入当前户号
            dic = {'name': 'user', 'value': f"{user_id}"}
            self.insert_expand_data(dic)
            # 写入剩余金额
            dic = {'name': 'balance', 'value': f"{balance}"}
            self.insert_expand_data(dic)
            # 写入最近一次更新时间
            dic = {'name': f"daily_date", 'value': f"{last_daily_date}"}
            self.insert_expand_data(dic)
            # 写入最近一次更新时间用电量
            dic = {'name': f"daily_usage", 'value': f"{last_daily_usage}"}
            self.insert_expand_data(dic)
            
            # 写入年用电量
            dic = {'name': 'yearly_usage', 'value': f"{yearly_usage}"}
            self.insert_expand_data(dic)
            # 写入年用电电费
            dic = {'name': 'yearly_charge', 'value': f"{yearly_charge} "}
            self.insert_expand_data(dic)

            if date: 
                for index in range(len(date)):
                    dic = {'date': date[index], 'usage': float(usages[index])}
                    # 插入到数据库
                    try:
                        self.db.insert_data(dic)
                        logging.info(f"The electricity consumption of {usages[index]}KWh on {date[index]} has been successfully deposited into the database")
                    except Exception as e:
                        logging.debug(f"The electricity consumption of {date[index]} failed to save to the database, which may already exist: {str(e)}")
            if month: 
                for index in range(len(month)):
                    try:
                        dic = {'name': f"{month[index]}usage", 'value': f"{month_usage[index]}"}
                        self.db.insert_expand_data(dic)
                        dic = {'name': f"{month[index]}charge", 'value': f"{month_charge[index]}"}
                        self.db.insert_expand_data(dic)
                    except Exception as e:
                        logging.debug(f"The electricity consumption of {month[index]} failed to save to the database, which may already exist: {str(e)}")
            if month_charge:
                month_charge = month_charge[-1]
            else:
                month_charge = None
                
            if month_usage:
                month_usage = month_usage[-1]
            else:
                month_usage = None
            # 写入本月电量
            dic = {'name': f"month_usage", 'value': f"{month_usage}"}
            self.insert_expand_data(dic)
            # 写入本月电费
            dic = {'name': f"month_charge", 'value': f"{month_charge}"}
            self.insert_expand_data(dic)
            # dic = {'date': month[index], 'usage': float(month_usage[index]), 'charge': float(month_charge[index])}
            self.db.close_connect()
        else:
            logging.info("The database creation failed and the data was not written correctly.")
            return
