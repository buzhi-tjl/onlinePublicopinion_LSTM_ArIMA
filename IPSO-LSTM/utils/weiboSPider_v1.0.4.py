import csv
import requests
import random
import selenium.common.exceptions
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from lxml import etree
import pandas
import json
import datetime
import time
import re
import os


class GetWeibo:
    def __init__(self):
        self.browser_options = Options()
        self.browser_options.add_argument('--no-sandbox')
        self.browser_options.add_argument('--disable-dev-shm-usage')
        self.browser_options.add_argument('--disable-gpu')
        # self.browser_options.add_argument('--headless=new')  # 如需无头模式取消注释
        self.browser = webdriver.Chrome(options=self.browser_options)
        self.browser.implicitly_wait(10)
        self.browser.set_page_load_timeout(30)

        self.headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.7444.176 Safari/537.36'}
        print("✅ 浏览器已成功创建。")

        self.base_url = 'https://s.weibo.com/weibo'
        self.keywords = None
        self.origin = None
        self.time_judge = None
        self.max_page = 50
        self.comment_dir = 'weibo_comment'
        self.unified_comment_file = os.path.join(self.comment_dir, "weibo_comment2.csv")
        if not os.path.exists(self.comment_dir):
            os.makedirs(self.comment_dir)
        self.main()

    # ---------- 新增：通过 API 获取微博详情 ----------
    def get_weibo_detail_by_api(self, weibo_id):
        """使用微博官方接口获取微博详情（转发、评论、点赞数等）"""
        url = "https://weibo.com/ajax/statuses/show"
        params = {"id": weibo_id}
        # 从浏览器获取 Cookie
        cookies = self.browser.get_cookies()
        cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
        headers = {
            "User-Agent": self.headers['user-agent'],
            "Cookie": cookie_str,
            "Referer": "https://weibo.com/",
            "X-Requested-With": "XMLHttpRequest",
        }
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            if "code" in data and data["code"] != 200:
                print(f"API 返回错误：{data}")
                return None
            return {
                "username": data.get("user", {}).get("screen_name", "未知账号"),
                "publish_time": self.parse_weibo_time(data.get("created_at", "")),
                "content": data.get("text_raw", "").replace('\n', ' ').strip(),
                "forward": data.get("reposts_count", 0),
                "comments_count": data.get("comments_count", 0),
                "likes": data.get("attitudes_count", 0),
                "uid": str(data.get("user", {}).get("id", "")),
            }
        except Exception as e:
            print(f"API 获取微博详情失败：{e}")
            return None

    def open_search(self):
        self.browser.get(self.base_url)
        self.browser.delete_all_cookies()
        time.sleep(2)
        print(f'✅ 微博搜索页面{self.browser.current_url}已成功打开...')

        # 加载 Cookie
        try:
            with open('data/cookies.txt', 'r', encoding='utf-8') as f:
                cookies_list = json.load(f)
                for cookie in cookies_list:
                    if isinstance(cookie.get('expiry'), float):
                        cookie['expiry'] = int(cookie['expiry'])
                    for key in ['sameSite', 'httpOnly', 'secure']:
                        if key in cookie:
                            del cookie[key]
                    if 'domain' not in cookie:
                        cookie['domain'] = '.weibo.com'
                    if '.weibo.com' in cookie['domain'] or 'weibo.com' in cookie['domain']:
                        self.browser.add_cookie(cookie)
            self.browser.refresh()
            time.sleep(3)
            print('✅ Cookie加载成功，已刷新页面使Cookie生效')
        except FileNotFoundError:
            print('⚠️ 未找到cookies.txt文件，请先保存登录后的Cookie，部分功能可能受限')
        except Exception as e:
            print(f'⚠️ Cookie加载失败：{str(e)}，请检查Cookie格式是否正确') 

        # 验证登录
        try:
            self.browser.get("https://weibo.com")
            time.sleep(3)
            WebDriverWait(self.browser, 10).until(
                EC.presence_of_element_located((By.XPATH, '//a[contains(@href, "/u/") or contains(text(), "我的主页")]'))
            )
            print('✅ 登录状态验证成功，已自动登录微博')
            self.browser.get(self.base_url)
            time.sleep(2)
        except:
            print('❌ 登录状态验证失败！Cookie可能无效，请重新获取并保存Cookie')
            input('登录完成后按回车键继续...')

        # 等待搜索框
        WebDriverWait(self.browser, 15).until(
            EC.element_to_be_clickable((By.XPATH, '//div[@class="searchbox"]//input[@type="text"]'))
        )

        kw = self.browser.find_element(By.XPATH,
                                       '//div[contains(@class, "searchbox")]/div[contains(@class, "search-input")]/input[@type="text"]')
        self.keywords = input('请输入微博搜索的关键词，按回车键确认：')
        print(f'搜索关键词为：{self.keywords}。')

        # 搜索范围
        while True:
            self.origin = input('搜索所有微博请输入1，按回车键确认，直接按回车键则只搜索原创微博：')
            if self.origin == '':
                self.origin = '&scope=ori'
                print('仅搜索原创微博。')
                break
            elif self.origin == '1':
                self.origin = '&typeall=1'
                print('搜索全部微博。')
                break
            else:
                print('输入错误，请重新输入。')
                continue
 
        # 截止时间
        # 选择截止时间（使用 strptime 验证）
        while True:
            date_time = input('请按年-月-日-时的格式输入抓取微博的发布截止时间（示例：2022-08-03-07），按回车键确认，直接按回车键则截止时间为当前时间：')
            if date_time == '':
                date_format = '%Y-%m-%d-%H'
                date_time = datetime.datetime.now().strftime(date_format)
                date_time = (datetime.datetime.strptime(date_time, date_format) + datetime.timedelta(hours=+1)).strftime(date_format)
                print('截止时间为：当前时间。')
                break
            else:
                try:
                    # 尝试验证格式
                    datetime.datetime.strptime(date_time, '%Y-%m-%d-%H')
                    print(f'截止时间为：{date_time}。')
                    break
                except ValueError:
                    print('时间格式输入错误！请使用“年-月-日-时”的格式，例如 2026-04-07-23。')
                    continue

        # 起始页
        while True:
            page_begin = input('请输入微博列表的抓取起始页（1至50之间），按回车键确认，直接按回车键从第1页开始：')
            if page_begin == '':
                self.start_page = 1
                print('抓取起始页为：第1页。')
                break
            elif re.match(r'([1-4]\d|50|^[1-9]$)', page_begin) is None:
                print('抓取起始页输入错误！请输入1-50之间的整数。')
                continue
            else:
                self.start_page = int(page_begin)
                print(f'抓取起始页为：第{self.start_page}页。')
                break

        # 最大页数
        while True:
            max_page_input = input(f'请输入最大抓取页数（默认50页，不能超过50），按回车键确认：')
            if max_page_input == '':
                self.max_page = 50
                print(f'最大抓取页数为：50页。')
                break
            elif re.match(r'([1-4]\d|50|^[1-9]$)', max_page_input) is None:
                print('最大页数输入错误（需1-50之间），请重新输入！')
                continue
            else:
                self.max_page = int(max_page_input)
                print(f'最大抓取页数为：{self.max_page}页。')
                break

        kw.clear()
        kw.send_keys(self.keywords)
        click_search = self.browser.find_element(By.XPATH,
                                                 '//div[contains(@class, "searchbox")]/button[contains(@class, "s-btn-b")]')
        click_search.click()
        time.sleep(3)

        date_format = '%Y-%m-%d-%H'
        date_past = (datetime.datetime.strptime(date_time, date_format) + datetime.timedelta(days=-31)).strftime(date_format)
        page_param = f'&page={self.start_page}' if self.start_page > 1 else ''
        search_url = f'https://s.weibo.com/weibo?q={self.keywords}{self.origin}&suball=1&timescope=custom:{date_past}:{date_time}&Refer=g{page_param}'
        self.browser.get(search_url)
        time.sleep(5)

        print(f'✅ 微博列表页面{self.browser.current_url}已成功打开，列表按时间倒序排序。')
        print(f'本次抓取配置：起始页{self.start_page}页 → 最大{self.max_page}页')
        print(f'抓取字段：微博账号, 微博id, 发文时间, 微博内容, 转发次数, 评论次数, 点赞次数')
        print(f'评论将保存到目录：{self.comment_dir}（统一文件：{self.unified_comment_file}）')
        print(f'本次抓取的开始时间是：{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        return self.browser.current_url, 0

    def auto_search(self, url, search_times):
        if url != self.browser.current_url:
            self.browser.get(url)
        print(f'\n📥 微博列表页面{self.browser.current_url}已打开，抓取中...')
        time.sleep(2)

        current_page_match = re.search(r'page=(\d+)', url)
        current_page = int(current_page_match.group(1)) if current_page_match else 1
        print(f'当前抓取页数：第{current_page}页 / 最大{self.max_page}页')

        if current_page > self.max_page:
            print(f'\n📌 已达到最大抓取页数{self.max_page}页，程序准备退出...')
            return None, search_times

        try:
            WebDriverWait(self.browser, 15).until(
                EC.presence_of_element_located((By.XPATH, '//div[contains(@class, "card")]'))
            )
        except:
            print('❌ 微博列表加载失败，跳过当前页')
            next_url = self._get_next_page_url(url)
            return next_url, search_times

        data = etree.HTML(self.browser.page_source)
        post_url = data.xpath('//p[contains(@class, "from")]/a[1]/@href') or data.xpath(
            '//div[contains(@class, "from")]/a[1]/@href') or data.xpath(
            '//div[contains(@class, "content")]//a[contains(@href, "weibo.com")]/@href')
        if not post_url:
            print('❌ 未找到微博链接，跳过当前页')
            next_url = self._get_next_page_url(url)
            return next_url, search_times

        df = pandas.DataFrame(columns=['微博账号', '微博id', '发文时间', '微博内容', '转发次数', '评论次数', '点赞次数'])

        for index, url_single in enumerate(post_url):
            full_url = 'https:' + url_single if not url_single.startswith('http') else url_single
            if 'weibo.com' not in full_url:
                print(f'❌ 无效URL：{full_url}，跳过')
                continue

            # 提取微博 ID（从 URL 中）
            weibo_id_match = re.search(r'/([A-Za-z0-9]+)(?:\?|$)', full_url)
            if not weibo_id_match:
                print(f'❌ 无法提取微博ID：{full_url}，跳过')
                continue
            weibo_id = weibo_id_match.group(1)
            print(f'\n🔍 处理第{index + 1}条微博（ID：{weibo_id}）：{full_url}')

            # ---------- 使用 API 获取微博详情 ----------
            detail = self.get_weibo_detail_by_api(weibo_id)
            if not detail:
                print(f'  - API 获取失败，跳过该微博')
                continue

            username = detail["username"]
            publish_time = detail["publish_time"]
            content = detail["content"]
            forward = detail["forward"]
            comments_count = detail["comments_count"]
            likes = detail["likes"]
            uid = detail["uid"]

            print(f'  - 基本信息：{username} | {publish_time} | 转发{forward} | 评论{comments_count} | 点赞{likes}')

            # 保存微博信息
            df.loc[len(df)] = [username, weibo_id, publish_time, content, forward, comments_count, likes]
            search_times += 1

            # 爬取评论（如果评论数 > 0）
            if comments_count > 0:
                print(f'  - 开始爬取评论（预计{comments_count}条）...')
                comment_df = self.get_weibo_comments(weibo_id, uid, "", None)  # refer_flag 已不重要
                if not comment_df.empty:
                    try:
                        if os.path.exists(self.unified_comment_file):
                            existing_comment_df = pandas.read_csv(self.unified_comment_file, encoding='utf_8_sig')
                            combined_comment_df = pandas.concat([existing_comment_df, comment_df], ignore_index=True)
                            combined_comment_df = combined_comment_df.drop_duplicates(subset='评论ID', keep='first')
                        else:
                            combined_comment_df = comment_df
                        combined_comment_df.to_csv(self.unified_comment_file, encoding='utf_8_sig', index=False)
                        print(f'  - 评论汇总保存完成：{self.unified_comment_file}（累计评论数：{len(combined_comment_df)}）')
                    except Exception as e:
                        print(f'  - 评论汇总保存失败：{str(e)}')
                else:
                    print(f'  - 未抓取到有效评论')
            else:
                print('  - 该微博无评论，跳过')

            # 每5条保存一次微博数据
            if search_times % 5 == 0:
                self._save_weibo_data(df, search_times)
                df = df.iloc[0:0]

        if not df.empty:
            self._save_weibo_data(df, search_times)

        next_url = self._get_next_page_url(url)
        if not next_url:
            print('\n📌 已到最后一页（未找到下一页）')
            return None, search_times

        return next_url, search_times

    # ---------- 以下方法基本保持不变（评论爬取、辅助函数等） ----------
    def extract_weibo_info(self, url):
        uid_match = re.search(r'/(\d+)/', url)
        if not uid_match:
            uid_match = re.search(r'/(\d+)\?', url)
        uid = uid_match.group(1) if uid_match else None
        weibo_id_match = re.search(r'/(\w+)\?', url)
        weibo_id = weibo_id_match.group(1) if weibo_id_match else None
        refer_flag = re.search(r'refer_flag=([^&]+)', url)
        refer_flag = refer_flag.group(1) if refer_flag else ""
        return uid, weibo_id, refer_flag

    def get_weibo_comments(self, weibo_id, uid, refer_flag, cookie=None, max_pages=50):
        base_url = "https://weibo.com/ajax/statuses/buildComments"
        comments_list = []
        next_param = ""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": f"https://weibo.com/{uid}/{weibo_id}",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if not cookie:
            browser_cookies = self.browser.get_cookies()
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in browser_cookies])
            headers["Cookie"] = cookie_str
        else:
            headers["Cookie"] = cookie

        for page in range(1, max_pages + 1):
            try:
                params = {
                    "is_reload": 1,
                    "id": weibo_id,
                    "is_show_bulletin": 2,
                    "is_mix": 0,
                    "uid": uid,
                    "fetch_level": 0,
                    "locale": "zh-CN"
                }
                if next_param:
                    params["max_id"] = next_param
                    print(f"📖 正在爬取第{page}页（next_param={next_param}）")
                else:
                    print(f"📖 正在爬取第{page}页（第一页）")

                response = requests.get(base_url, params=params, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()

                if not data or "data" not in data or len(data["data"]) == 0:
                    print(f"❌ 第{page}页无评论数据，停止爬取")
                    break

                for comment in data["data"]:
                    reply_count = comment.get("total_number", 0)
                    id_comment = comment.get("id", 0)
                    comments_list.append({
                        "评论ID": comment.get("idstr", ""),
                        "用户昵称": comment.get("user", {}).get("screen_name", ""),
                        "用户ID": comment.get("user", {}).get("idstr", ""),
                        "评论内容": comment.get("text_raw", ""),
                        "发布时间": self.parse_weibo_time(comment.get("created_at", "")),
                        "点赞数": comment.get("like_counts", 0),
                        "回复数": comment.get("total_number", 0)
                    })
                    if reply_count > 0:
                        try:
                            time.sleep(random.randint(1, 3))
                            self.crawl2(base_url, uid, weibo_id, refer_flag, id_comment, "0", comments_list, headers)
                        except Exception as e:
                            print(f"调用crawl2时出错: {e}")

                next_param = data.get("max_id", "")
                print(f"✅ 第{page}页爬取完成，共{len(data['data'])}条评论")
                if not next_param:
                    print(f"📌 已爬取完所有评论，共{page}页，总计{len(comments_list)}条")
                    break
                time.sleep(1)
            except Exception as e:
                print(f"❌ 第{page}页爬取失败：{str(e)}")
                break

        return pandas.DataFrame(comments_list)

    def _parse_num(self, elem_text):
        if not elem_text:
            return 0
        num_str = ''.join(elem_text).strip()
        if num_str in ['转发', '评论', '赞', '回复', ' 转发 ', ' 评论 ', ' 赞 ', ' 回复 ']:
            return 0
        if '万' in num_str:
            try:
                return int(float(num_str.replace('万', '')) * 10000)
            except:
                return 0
        num_clean = re.sub(r'\D', '', num_str)
        return int(num_clean) if num_clean else 0

    def _save_weibo_data(self, df, search_times):
        try:
            is_first_save = not os.path.exists('weibo_spider.csv') or os.path.getsize('weibo_spider.csv') == 0
            df = df.drop_duplicates(subset='微博id', keep='first').reset_index(drop=True)
            df.to_csv(
                'weibo_spider.csv',
                mode='w' if is_first_save else 'a',
                encoding='utf_8_sig',
                header=is_first_save,
                index=False,
                quoting=csv.QUOTE_MINIMAL
            )
            print(f'\n💾 已保存{search_times}条微博信息至：weibo_spider.csv')
        except Exception as e:
            print(f'❌ 保存微博数据失败：{str(e)}')

    def _get_next_page_url(self, current_url):
        try:
            next_btn = WebDriverWait(self.browser, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//a[@class="next" and contains(text(), "下一页")]'))
            )
            next_url = next_btn.get_attribute('href')
            if next_url and 'page=' in next_url:
                return next_url
        except:
            pass
        current_page = 1
        if 'page=' in current_url:
            current_page_match = re.search(r'page=(\d+)', current_url)
            if current_page_match:
                current_page = int(current_page_match.group(1))
        next_page = current_page + 1
        if next_page > self.max_page:
            return None
        if 'page=' in current_url:
            return re.sub(r'page=\d+', f'page={next_page}', current_url)
        else:
            return current_url + f'&page={next_page}'

    def setFirstParams(self, id, max_id):
        params = {
            "is_reload": "1",
            "id": id,
            "is_show_bulletin": "2",
            "is_mix": "1",
            "fetch_level": "1",
            "max_id": max_id,
            "count": "20",
            "uid": "1224900857",
            "locale": "zh-CN"
        }
        return params

    def crawl2(self, url, uid, weibo_id, refer_flag, id, max_id, comments_list, headers):
        headers["Referer"] = f"https://weibo.com/{uid}/{weibo_id}?refer_flag={refer_flag}"
        i = 1
        try:
            response = requests.get(url=url, params=self.setFirstParams(id=id, max_id=max_id), headers=headers)
            print(f"二级评论请求状态码: {response.status_code}")
            try:
                response_data = response.json()
            except json.JSONDecodeError as e:
                print(f"JSON解析错误: {e}")
                print(f"响应内容: {response.text[:500]}")
                return None, None
            if "data" not in response_data:
                print(f"响应中没有data字段: {response_data}")
                return None, None
            data_list = response_data["data"]
            for data in data_list:
                try:
                    comments_list.append({
                        "评论ID": data.get("idstr", ""),
                        "用户昵称": data.get("user", {}).get("screen_name", ""),
                        "用户ID": data.get("user", {}).get("idstr", ""),
                        "评论内容": data.get("text_raw", ""),
                        "发布时间": self.parse_weibo_time(data.get("created_at", "")),
                        "点赞数": data.get("like_counts", 0),
                        "回复数": data.get("total_number", 0)
                    })
                    print(f"本页第{i}条评论已爬取")
                    i += 1
                    id = str(data["id"])
                    max_id = str(response_data["max_id"])
                except KeyError as e:
                    print(f"数据字段缺失: {e}, 跳过此条数据")
                    continue
            if response_data.get("max_id", 0) != 0:
                try:
                    time.sleep(random.randint(1, 3))
                    self.crawl3(url, uid, weibo_id, refer_flag, id, max_id, comments_list, headers)
                except Exception as e:
                    print(f"调用crawl3时出错: {e}")
            return id, max_id
        except Exception as e:
            print(f"crawl2函数出错: {e}")
            return None, None

    def setSecondParams(self, id, max_id):
        params = {
            "flow": "1",
            "is_reload": "1",
            "id": id,
            "is_show_bulletin": "2",
            "is_mix": "1",
            "fetch_level": "1",
            "max_id": max_id,
            "count": "20",
            "uid": "1224900857",
            "locale": "zh-CN",
        }
        return params

    def crawl3(self, url, uid, weibo_id, refer_flag, id, max_id, comments_list, headers):
        headers["Referer"] = f"https://weibo.com/{uid}/{weibo_id}?refer_flag={refer_flag}"
        print("开始爬取二级评论的下一页!")
        try:
            response = requests.get(url=url, params=self.setSecondParams(id=id, max_id=max_id), headers=headers)
            print(f"二级评论下一页请求状态码: {response.status_code}")
            try:
                response_data = response.json()
            except json.JSONDecodeError as e:
                print(f"JSON解析错误: {e}")
                print(f"响应内容: {response.text[:500]}")
                return None, None
            if "data" not in response_data:
                print(f"响应中没有data字段: {response_data}")
                return None, None
            data_list = response_data["data"]
            for data in data_list:
                try:
                    comments_list.append({
                        "评论ID": data.get("idstr", ""),
                        "用户昵称": data.get("user", {}).get("screen_name", ""),
                        "用户ID": data.get("user", {}).get("idstr", ""),
                        "评论内容": data.get("text_raw", ""),
                        "发布时间": self.parse_weibo_time(data.get("created_at", "")),
                        "点赞数": data.get("like_counts", 0),
                        "回复数": data.get("total_number", 0)
                    })
                    id = str(data["id"])
                    max_id = str(response_data["max_id"])
                except KeyError as e:
                    print(f"数据字段缺失: {e}, 跳过此条数据")
                    continue
            if response_data.get("max_id", 0) != 0:
                try:
                    time.sleep(random.randint(1, 3))
                    self.crawl3(url, uid, weibo_id, refer_flag, id, max_id, comments_list, headers)
                except Exception as e:
                    print(e)
            return id, max_id
        except Exception as e:
            print(f"crawl3函数出错: {e}")
            return None, None

    def parse_weibo_time(self, time_str):
        try:
            dt = datetime.datetime.strptime(time_str, '%a %b %d %H:%M:%S %z %Y')
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            return time_str

    def main(self):
        search_times = 0
        start_time = datetime.datetime.now()
        try:
            url, search_times = self.open_search()
            while url:
                url, search_times = self.auto_search(url, search_times)
                if not url:
                    break
        except Exception as e:
            print(f'\n❌ 程序主流程出错：{str(e)}')
        finally:
            run_time = (datetime.datetime.now() - start_time).total_seconds()
            minutes = int(run_time // 60)
            seconds = int(run_time % 60)
            self.browser.quit()
            print(f'\n📊 程序退出汇总：')
            print(f'  - 共抓取微博：{search_times}条')
            print(f'  - 微博数据文件：weibo_spider.csv')
            comment_count = 0
            if os.path.exists(self.unified_comment_file):
                try:
                    comment_df = pandas.read_csv(self.unified_comment_file, encoding='utf_8_sig')
                    comment_count = len(comment_df)
                except:
                    comment_count = len(os.listdir(self.comment_dir)) if os.path.exists(self.comment_dir) else 0
            print(f'  - 累计评论数：{comment_count}条（文件：{self.unified_comment_file}）')
            print(f'  - 运行时间：{minutes}分{seconds}秒')
            print(f'  - 退出时间：{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')


if __name__ == '__main__':
    gt = GetWeibo()