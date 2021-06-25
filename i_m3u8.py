import time
import requests
import m3u8
from Crypto.Cipher import AES
import os
from datetime import datetime
import threading
import shutil

import urllib3

thread_num = 600  # 线程数量

# todo 注意是否已关闭了verify验证


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class temp_file:
    def __init__(self, tmp_filepath):
        self.filepath = tmp_filepath

    def save(self, ts_urls, mod="w"):
        with open(self.filepath, mod) as file:
            return file.write(ts_urls)

    def delete(self):
        os.remove(self.filepath)

    def load(self, mod="r"):
        empty_tmp = []
        if not os.path.exists(self.filepath):
            return empty_tmp
        with open(self.filepath, mod) as file:
            r = file.read()
        return r.split("\n")

    def status(self):
        if not os.path.exists(self.filepath):
            return "无缓存"
        else:
            return "有缓存"


def merge_ts(ts_files, drama, filename, path_ts=".ts"):  # 合并下载后的ts文件
    status = True  # 发现合成过程的问题
    for ts in ts_files:
        with open(path_ts + "/" + ts, "rb") as file:
            ts_res = file.read()
            if len(ts_res) == 0:
                print("合成错误！")
                status = False
                return status
        with open(drama + "/" + filename, "ab") as file2:
            file2.write(ts_res)
    return status


def del_file(filepath):
    """
    删除某一目录下的所有文件或文件夹
    :param filepath: 路径
    :return:
    """
    del_list = os.listdir(filepath)
    for f in del_list:
        file_path = os.path.join(filepath, f)
        if os.path.isfile(file_path):
            os.remove(file_path)
        elif os.path.isdir(file_path):
            shutil.rmtree(file_path)


def download_ts(ts_url, key_res, tmp_ts_urls, ts_urls_list, path_ts=".ts"):  # 线程下载文件，保存在文件夹ts中
    # 头部文件
    # headers = {"Host": "vod5.wenshibaowenbei.com",
    #           "Origin": "https://r.tvkanba.com",
    #           "Connection": "keep-alive",
    #           "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    #                         "Chrome/91.0.4472.101 Safari/537.36 Edg/91.0.864.48 "}
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/91.0.4472.114 Safari/537.36 Edg/91.0.864.54 ",
               "Connection": "keep-alive"
               }
    # todo 设置超时重连机制
    i = 0
    while i < 4:
        try:
            # 缓冲区大小
            buffer_size = None
            session = requests.session()

            ts = session.get(ts_url, timeout=(3, 80), stream=True,
                             headers=headers, verify=False)  # 通过缓冲获取
            # 获取ts文件名filename
            filename_ts = ts_url.split("/")[-1]
            with open(path_ts + "/" + filename_ts, "ab") as file:
                # 密文长度不为16的倍数，则添加b"0"直到长度为16的倍数
                # buffer_size 为None时，stream=True则读取接收到的数据块大小；
                # todo 这里可能存在内存满了的情况； buffer_size 为None时，下载多少就读取多少；
                for ts_data in ts.iter_content(buffer_size):
                    while len(ts_data) % 16 != 0:
                        ts_data += b"0"  # decrypt方法的参数需要为16的倍数，如果不是，需要在后面补二进制"0"
                    if key_res:  # 根据是否存在key判断解密
                        # print("解密...",key_res)
                        sprytor = AES.new(key_res, AES.MODE_CBC, IV=key_res)
                        file.write(sprytor.decrypt(ts_data))
                    else:
                        file.write(ts_data)
            # 这里才是保存进度文件的地方
            # 保存下载进度 每次都是全文覆盖，反正也没有多少byte
            # 记录下载信息
            ts_urls_list.append(ts_url)
            tmp_ts_urls.save("\n".join(ts_urls_list))
            return True
        except requests.exceptions.RequestException:
            print('超时，重连中...%d' % i)
            i += 1
    raise Exception("三次重连失败，文件下载失败。")


def down_m3u8(m3u8_url, drama, filename, path_ts=".ts"):
    # 获取m3u8文件内容
    m3u8_video = m3u8.load(m3u8_url)
    ts_urls = []
    ts_files = []
    # 获取ts_urls 需要下载的列表
    if not m3u8_video.segments:  # 判断是否为变异m3u8
        print("变异m3u8...")
        # todo 这里需要判断是否为采用了分辨率的设置
        for playlist in m3u8_video.playlists:
            ts_urls.append(playlist.absolute_uri)
        ts_playlist = m3u8_video.playlists

        # 判断m3u8是否为m3u8
        if len(ts_urls) == 1 and ts_urls[0].find("m3u8"):
            print("获取M3U8资源...")

            return down_m3u8(m3u8_url=ts_urls[0], drama=drama, filename=filename)
        else:
            # todo 这里说明m3u8存在多个分辨率
            # print(ts_playlist)
            for ts_stream in ts_playlist:
                print(ts_stream.stream_info)
            no = input("视频存在%d个不同分辨率(0,1,2等)：" % len(ts_urls))
            ts_select = ts_playlist[int(no)]
            return down_m3u8(m3u8_url=ts_select.absolute_uri, drama=drama, filename=filename)
    else:
        print("识别m3u8成功...")
        for i, seg in enumerate(m3u8_video.segments):
            ts_urls.append(seg.absolute_uri)
            ts_files.append(seg.absolute_uri.split("/")[-1])
    keys = m3u8_video.keys  # 尝试获取keys
    if len(keys) != 0 and keys[0] is not None:
        key = keys[0]
        key_res = requests.get(key.absolute_uri).content
        print("获取key成功", key_res)
    else:
        key_res = ""
        # todo 这里可能需要手动填写keys 特别是某些key是需要下载的
        print("无加密视频,请检查是否有其它key url")
    # 保存ts_files列表文件
    tmp_ts_files = temp_file("ts_files.tmp")
    tmp_ts_files.save("\n".join(ts_files))  # 保存ts_files文件
    # 创建缓存进度文件
    tmp_ts_urls = temp_file("m3u8.tmp")
    ts_urls_down = tmp_ts_urls.load()
    print("加载进度...")
    # 创建多线程  thread_num
    for ts_urls_thread in [ts_urls[i:i + thread_num] for i in range(0, len(ts_urls), thread_num)]:
        print(f"进行一组{thread_num}个下载...")
        threads = []
        for ts_url in ts_urls_thread:
            ts_name = ts_url.split("/")[-1]  # ts文件名
            if ts_url not in ts_urls_down:
                #  todo 代理
                #  多线程下载
                thread = threading.Thread(target=download_ts, name="下载线程",
                                          args=(ts_url, key_res, tmp_ts_urls, ts_urls_down))
                thread.start()
                threads.append(thread)
                print("正在下载：" + ts_name,
                      str(round((len(ts_urls_down) / len(ts_urls)) * 100, 2)) + "%")
            else:
                # print(ts_url, "已下载")
                pass
        print("等待线程任务完成...")
        for t in threads:
            t.join()  # 附着于主进程
            print("剩余未完成任务:", threading.activeCount() - 1)
    print("合成...")
    m_res = merge_ts(ts_files=ts_files, drama=drama, filename=filename)
    if m_res:
        now = datetime.now()
        date_time = now.strftime("%Y-%m-%d, %H:%M:%S")
        print(filename, "下载完成", date_time)
        tmp_ts_urls.delete()  # 删除进度文件
        tmp_ts_files.delete()  # 删除合成文件
        del_file(path_ts)  # 删除.ts文件夹中所有文件
    else:
        print("合成过程中出现问题。\n可能是因为还没下载完成，请尝试重启程序继续下载。")


if __name__ == "__main__":
    url = "https://cdn24.pztv.ca/upload/20191025/979ef1f73d3943c666b5748f8b5e13f2/979ef1f73d3943c666b5748f8b5e13f2.m3u8"
    file_name = "4.mp4"
    drama_text = "实习医生格蕾 第十六季"
    print(time.asctime(time.localtime(time.time())))
    down_m3u8(m3u8_url=url, drama=drama_text, filename=file_name)

# todo 未完成问题列表
# 1.多线程下载文件  这个问题目前有一种解决方法，就是把所有ts文件下载并保存在tmp_ts文件夹中；等所有ts文件下载完毕，然后通过index.m3u8
# 里面的ts文件顺序进行整合成mp4文件
# 2.另外的解决办法

# 关于m3u8的几个注意点
# 解密，new有三个参数，
# 第一个是秘钥（key）的二进制数据，
# 第二个使用下面这个就好
# 第三个IV在m3u8文件里URI后面会给出，如果没有，可以尝试把秘钥（key）赋值给IV
