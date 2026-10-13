# -*- coding: utf-8 -*-
# 汽水音乐  TVBox / 影视仓 py 源
# 站点: 字节「汽水音乐」Web 接口 https://api.qishui.com
#
# 端点(2026-10-13 全部实测可用, 无需登录):
#   POST /luna/feed/mode                       听歌模式墙  feed_mode_block[].feed_mode[].entity.feed_scene_mode
#   POST /luna/discover                        发现页      blocks[].inner_block[].resources[]
#   POST /luna/discover/mix                    发现页补充混合流
#   GET  /luna/charts/<chart_id>               榜单        chart.track_ranks[]
#   POST /luna/feed/radio/tracks               电台曲目    items[]  {radio_id, flow_type, full_media,...}
#   POST /luna/playlist/detail                 歌单曲目    media_resources[].entity.track_wrapper.track
#   POST /luna/search/track?device_platform=web        搜歌   result_groups[tracks].data[]
#   POST /luna/search/playlist?device_platform=web     搜歌单 result_groups[playlists].data[]
#   POST /luna/search/listen_video?device_platform=web 听抖音 result_groups[listen_video].data[]
#   GET  /luna/h5/seo_track?track_id=&device_platform=web   取流  track_player.video_model.video_list[]
#
# 取流要点:
#   - video_list 每项 = {video_meta:{quality,bitrate,codec_type,size,...}, main_url, backup_url}。
#     quality 取值 medium(≈65k) / higher(≈129k) / highest(≈257k)。
#   - ★档位数量由歌曲本身决定(常见 1~3 档); 匿名最高到 highest(~257kbps), 拿不到无损档。
#   - 带 encrypt_info 的档位是加密流, 跳过不用; 实测匿名返回的各档均无 encrypt_info。
#   - 备用源: track_player.url_player_info 是 vod-luna 的 GetPlayInfo 地址,
#     其 PlayInfoList 与 video_list 同源同档, 仅在 video_list 为空时兜底。
#
# 听抖音要点:
#   - ★必须带 device_platform=web, 否则一律 0 条。
#   - ★搜索词用「推荐 / 音乐」等有结果; 用「热门视频」返回 0 条(踩过的坑)。
#   - 播放: aweme.snssdk.com/aweme/v1/play/?video_id=<vid>&ratio=1080p&line=0
#     (HEAD 200 video/mp4; 注意用 vid(字符串) 不是 video_id(数字))。
#
# 播放地址格式 / 「能播没声音」结论(2026-10-13 实测 + 用户反馈校正):
#   - 官方主源 = MP4/M4A 容器(ftyp="M4A ") + AAC-LC 44.1kHz 立体声, 三档 65k/129k/257k;
#     第三方源 = MP3(酷我 kwyy, ~320k, audio/mpeg) —— **现仅供「VIP替代」线路使用**
#     (第三方 MP3 兼容线路已于第十轮整体移除, 见文末「第十轮」)。
#   - 容器层完全正常(已逐字节核对): moov 在文件头(faststart) / hdlr=soun / stsd=mp4a /
#     esds 完整(csd-0=1210 → AAC-LC 44.1k 立体声) / elst 正常 / Range 206 / ffmpeg
#     volumedetect mean -16.6dB(有声音, 非静音非加密)。★即「源侧/流本身」无任何问题。
#   - ★根因(关键证据: 用户确认「原版(蜜果版)有声音」):
#     原版实际返回的是**第三方(酷我)的 MP3 直链**(它的 VIP 判定过宽, 几乎每首都走
#     这条路), 直连 CDN、带 music_player:1 → 用户播放器有声。
#     本 sky 版一度: ① 走汽水官方 audio-only M4A(无后缀 + Content-Type: video/mp4);
#                    ② 又加了本地代理, 把 URL 改成 http://127.0.0.1:<port>/audio/xxx.m4a。
#     ② 是致命的 —— 播放器不接受 loopback 地址, 整条线路全部无声。
#   - ★因此本版默认形态 = 直连上游(不走代理) + music_player:1。本地代理降级为实验特性,
#     默认关闭(见下方开关)。
#     ★(第十轮更新) 当年为兜底还额外插过一条第三方 MP3 线路并排在最前; 现官方档位在 App
#     侧关掉「音频直通」后已能正常出声 → 该线路**已整体移除**, 线路列表回到纯官方档位。
#
# ★★「走 App(汽水官方流) 能不能出声」——已找到可落地的做法(2026-10-13 实测):
#   - 官方音频是 audio-only 的 M4A(media_type=audio, vtype=m4a, AAC-LC), 在 /video/tos/...
#     路径下分发, 响应头 Content-Type **随 CDN 节点而异**:
#        v26-luna / v11-luna / v5-se-*-luna → **audio/mp4**(播放器认音频, 有声)
#        v5-ex-luna / v5-luna             → video/mp4(播放器当视频起链, 无声)
#     两者字节 100% 相同(md5 核对: 头 256KB + 尾 8KB 全等), 只有响应头不同。
#   - 同一 URL 的 Content-Type 是**粘滞**的(同一客户端连续 8 次 HEAD 结果一致) →
#     「先用 HEAD 探出 audio/mp4 的地址再交给播放器」可靠。
#   - 每首曲目有 12 个候选地址(seo 的 main/backup × 各档 + 备用端点 url_player_info
#     的 VOD GetPlayInfo main/backup × 各档), 实测至少 6 个是 audio/mp4。
#   - 换 CDN 域名无效(签名绑定 host, 一律 403); 路径加 .m4a 也 403; 追加任意 query
#     参数不影响(CDN 忽略未知参数); CDN 对 UA/Referer 完全不挑(任意 UA 都 200)。
#   → 实现: `_app_audio_url()` 播放官方档位时逐个候选 HEAD 探测, 取第一个 audio/* 的;
#     找不到则回落 main_url。开关见下 "app_probe"。
#
# ★★ 第三方完整音源(酷我直连)提速(2026-10-13 第五轮; 现服务「VIP替代」线路):
#   - 旧实现走第三方聚合站 yx520(它再代理酷我), 实测冷启 2.4s / 热 1s, 再加一次 seo_track
#     回查 → 起播要 1.5~3s。
#   - 现改为**直连酷我官方接口**: ① search.kuwo.cn/r.s 搜歌 → rid; ② nmobi.kuwo.cn/mobi.s
#     (convert_url_with_sign) 取流。实测**搜索+取流合计 0.12~0.19s**, 且拿到的 320k mp3
#     与聚合站返回的是**同一份文件**(字节数一致, 例如稻香 8940938B)。
#   - ★坑: 高码率必须写 `br=320kmp3`(带单位); 写成 `bitrate=320kmp3` 服务端只给 128k。
#     另有无损档 `br=2000kflac&format=flac`(~26MB, audio/x-flac)可用, 默认不启用。
#   - 再加两道提速: ① 线路 id 里直接编入「歌名+歌手」(_pack("m",{...})), 播放时省掉一次
#     seo_track 回查; ② 打开详情时**后台线程预热**直链(_prefetch_alt), 用户按下播放前
#     多已命中内存缓存 → 秒开。同曲 900s 内重播零网络等待。
#   - 聚合站 yx520 保留为**兜底**(酷我直连失败时才用)。
#   ★(第十轮) 依赖这套取流链的**「MP3 兼容线路」已整体移除** —— 官方档位在 App 侧关掉
#     「音频直通」后能正常出声, 它失去了存在理由。现仍用它的只有「VIP替代」(会员/试听曲
#     官方只放 ~60s 片段, 需要第三方完整版)。
#
# ★★「EXO 内核无声」根因与修复(2026-10-13 第六轮; 用户反馈「只有 EXO 播放无音, MPV/IJK 正常」):
#   现象: 同一源下, 酷我 MP3 线路在 EXO 上有声, 而汽水官方档位无声; 换 MPV/IJK 则全部有声。
#   实测(逐字节, qs_exo_verify.py): 官方 M4A 容器与编码完全正常 ——
#     ftyp="M4A " / moov 在文件头(faststart) / 无 moof / hdlr=soun / stsd=mp4a /
#     AAC-LC 44.1kHz 立体声 257k / 未加密 / Range 206 / Content-Type: audio/mp4。
#     → 流本身没有问题, 问题在播放器的「音频/视频路径」判定。
#   ★根因(读 App 源码确认): 播放器用 `AudioUtil.isAudio(result)` 决定这条流走**音频播放
#     路径(AudioActivity)** 还是普通视频路径, 判据只有两条:
#         if (format != null && format.toLowerCase().contains("audio")) return true;   // ①
#         return isAudioUrl(url) || isAudioUrl(realUrl());                              // ②
#         // isAudioUrl(): 先把 `?` 与 `#` 之后的内容截掉, 再 endsWith(.mp3/.m4a/.flac/...)
#     官方档位 URL = `.../video/tos/cn/.../<id>?<query>` —— **没有任何后缀**, 两条判据
#     都不满足 → 被当作视频起链 → **能播但没声音**; 酷我 MP3 以 `.mp3` 结尾 → 判为音频 → 有声。
#     (旁证: `PlaybackResourceClassifier.hasProgressiveExtension()` 用同一套后缀表, 并且
#      同样截断 `?`/`#`, 所以「往 query 或 fragment 里补后缀」这条路走不通。)
#   ★★结论修正(2026-10-13 第八轮, 读 App 源码 + 用户确认播放样式后定案):
#     ① 的判断本身是对的(`format` 含 "audio" → `AudioUtil.isAudio()` 直接 true), 但
#     **用户已确认其播放样式是「沉浸式(默认)」**, 而沉浸式下所有 `AudioActivity.startIfAudio`
#     入口第一行就是 `if (PlayerSetting.isImmersiveAudioMode()) return false;`
#     → **此模式下 format 全程不生效**。
#     因此: 「加了 format 才播不了」这个归因**不成立**(format 在该模式下等于没加)。
#     `audio_format` 保持默认 0, 理由退化为最简单的一条: 原版就没这个字段, 保持原样。
#   ⚠️ 归因史(留档避免再绕): 本轮先后给出过两个都不够硬的解释 ——
#     (1)「format 只落到 media3 的 MediaItem.mimeType, 故无害」→ 不完整, 它还会命中
#        App 的**音频/视频分流**判据 `AudioUtil.isAudio()`(只是沉浸式下走不到);
#     (2)「是 format 把官方档位分流进 AudioActivity 才播不了」→ 前提(非沉浸式)不成立。
#     已确认的**硬事实**只有一条: 用户设备上官方档位「一直转圈/黑屏」, 且只有官方档位。
#   ⚠️ 与本版 media3 无关: `MediaItem.Builder.setMimeType(format)` → `Util
#      .inferContentTypeForUriAndMimeType()`, 只有 4 个清单 MIME(*.mpd/*.m3u8/*.ism/
#      *.rtsp)会改变 MediaSource 类型, 其余一律 ProgressiveMediaSource + 嗅探。
#   → (第十轮更新) 官方档位在 App 侧关掉「音频直通」后已能出声, 源侧不再需要第三方兜底线路;
#     当年那条「第三方 MP3 排最前」的策略与线路**已整体移除**。
#
# ★★★「EXO 能播但没声音」根因已定案(2026-10-13 第九轮) —— **不是源的问题, 源侧修不了**:
#   症状: 官方档位(汽水 AAC/M4A)在 EXO 内核下**能播、进度在走、但完全没声音**;
#         同源的第三方 MP3 线路在 EXO 下有声; 切 MPV/IJK 全都有声。
#   根因是 App 的**音频直通(encoded bypass)**, 链路(App 源码已逐条核对):
#     1) `KernelPerformanceSetting.isAudioPassThrough(kernel)`
#        = `Prefers.getBoolean("...audio_pass_through", true)` → **默认开启**(EXO/MPV 各一份)。
#     2) `ExoUtil.buildAudioSink()` 用它决定音频输出链, 并把 `ExoCompressedAudioDirectPolicy`
#        挂到 AudioTrack 输出提供者上。
#     3) 该 policy 的白名单 = **MP3 / AAC-LC / AAC-HE v1,v2 / AAC-XHE / AAC-ELD**;
#        若设备的 `AudioManager.getDirectPlaybackSupport()` 也判支持, 就标成
#        `FORMAT_SUPPORTED_DIRECTLY` —— 即 **不解码, 把压缩帧直接塞给 AudioTrack/DSP**。
#     4) 它**只在初始化失败 / write 抛异常时**才回退 PCM。「DSP 收下数据但不出声」不产生
#        任何异常 → **不回退 → 永久静音**。App 自己的 UI 文案就是这么写的(EXO「音频直通」):
#        「出现无声立即关闭。代价：输出链不支持时不会自动变成可播放音频。」
#     5) 自洽性: 同源内 MP3 的 direct 路径能出音、AAC 的静默失败, 是两条独立路径, 可以不成;
#        MPV 正常是因为它要求先有 passthrough 输出设备(`MpvAudioCapabilities`), 否则走 PCM;
#        而 EXO 的 vendor-direct 不要求, 更激进所以更容易踩到静默失败。
#   → **修复只能在 App 侧**(设置, 不是源): 播放性能 → 选 EXO 内核 → 关「音频直通」;
#     仍无声再开「音频软解优先」; 都不行就用 MPV 内核。
#   → **源侧无解**: 直通判定只看解码器解析出的 `Format`(encoding/sampleRate/channelMask),
#     URL、header、`format` 字段都改变不了它 —— 不要再试图用 `format` 去影响它(见上文)。
#   → 确认手段: 打开调试日志(类别含 ALL), 看标签 `exo-audio-direct` 的
#     `reason=vendor-direct`(即命中直通) / `standard-offload` / `no-direct-support`。
#
# ★★★ 第十轮(2026-10-13): **移除第三方 MP3 兼容线路**
#   背景: 那条「MP3源」是第一/二轮为了「官方档位在 EXO 下不出声」而加的兜底线路, 当时把它
#         排在最前以保证「至少有个能听的声音」。
#   依据: 第九轮已把「EXO 无声」定案为 App 侧「音频直通」问题; 用户关掉该开关后反馈
#         **「官方档位 能播」** → 兜底理由消失。而它每首曲子都多加一条冗余线路, 详情页
#         还要多跑一次第三方取流预热, 属于纯粹的成本。
#   改动: 1) `_track_detail` / `_playlist_card` 不再补 MP3 线路 → 线路列表 = 纯官方档位
#            (+ 会员曲的「VIP替代」, 那是为官方 60s 试听片段准备的, 与本轮无关, **保留**);
#         2) 删除 `_with_mp3()` 方法与 `prefer_mp3` 开关;
#         3) `_third_party_play()` / `_alt_url()` / `_prefetch_alt()` **保留** ——
#            「VIP替代」仍依赖它们;
#         4) `playerContent` 里 `quality == "mp3"` 分支保留, 仅用于兼容**历史缓存列表**
#            中的旧 id(新列表不再产生这种 id), 命中后回落官方最高档。
#
# ★★★ 第十一轮(2026-10-13): **听歌模式改用官方数据源 + 曲目量补足到 50**
#   用户反馈: 「听歌模式里获取的列表和汽水音乐里对应模式获取的列表不一样, 有些模式下是
#             按模式名字搜索的列表; 获取的播放列表数据太少, 让获取不少于 50; 官方可以点
#             查看更多继续加载」。
#   旧实现的问题(三处, 全都在 `_collection_detail`):
#     ① `kind="preference"`(默认/熟悉/新鲜) 用 **热歌榜 / 怀旧电台 / 新歌榜** 顶替 ——
#        纯属猜测, 和官方「推荐/熟悉/新鲜」是三套不同的东西;
#     ② `kind="scene"`(45 个场景模式) 落进 else 分支 → **按模式名去搜索** —— 就是用户
#        看到的「按模式名字搜索的列表」;
#     ③ 电台一次只拿 6 首; 榜单/歌单也没保证 ≥50。
#   ★官方真实数据源(全部实测确认, 权威实现见 github Laine127/libresoda `soda/feed.rs`,
#     上游 guohuiyuan/music-lib; 端点与参数已逐条复核):
#     - 听歌模式列表   `POST /luna/pc/feed/mode`   (源里用 /luna/feed/mode, 等价)
#     - **模式内容流** `POST /luna/pc/discover/mix`
#         body = {block_type:"discovery_playlist", sub_channel_id:0,
#                 exposure_radio_list:[], cursor:"", count:20,
#                 scene_mode_id:<场景号>}          ← 场景模式
#                / {..., mode:"default|familiar|fresh"}  ← 偏好模式
#         返回 `inner_block[].resources[].entity.playlist` = 该模式下的**歌单**。
#     - 主数据源: **`POST /luna/pc/discover/mix`** 的官方推荐歌单池(保持服务端顺序), 用
#       `POST /luna/playlist/detail`(count=300) 展开成曲目。实测一个歌单动辄 100+ 首
#       (「经典摇滚入坑指南」121 首), 所以 **1~2 次请求即可凑够 50 首**(约 1~1.5s)。
#     - `POST /luna/pc/feed/song-tab`(官方推荐队列, `items[].entity.track_wrapper.track`)
#       虽是"进模式后真正播放的流", 但实测每次固定 6 首、忽略 count, **且对所有
#       `scene_mode_id` / `mode` 返回的是同一条随机流**(7 个模式的前 3 首几乎完全一样)
#       → 用它会让所有模式长得一模一样, 还慢 3 倍。故**不采用**(留档备查)。
#     ⚠️ **未登录拿不到「场景专属流」**(重要实测, 别再重复踩):
#       - `scene_mode_id` 对 discover/mix **基本不过滤** —— 同一场景连采样 4 次, 歌单集合
#         **零交集**; 跨场景交集率(5~9 / 33)与「完全不带场景」的基线相同。早先单次采样
#         看到的「动感健身→刷脂电音」只是巧合。
#       - `song-tab` 的 `scene_mode_id` / `queue_type` / `sub_queue_type` / `feed_scene_mode`
#         也全部无效(9 种参数变体结果无差异)。
#       - `/luna/pc/feed/mode/{cutover,switch,start,select,set}` 全部 **404**
#         —— 不存在"切换/开启模式"的接口。
#       → 汽水的「听歌模式」对未登录请求更像 **UI + 推荐权重的提示**(feed_mode 条目里带的
#         是 `cutover_toast`/`game_play_info` 这类 UI 字段), 服务端仍返回同一个随机推荐池。
#         参数已全部透传, 登录态下服务端若认就会自动生效; 源侧不依赖它做过滤。
#   ⚠️ 电台(`/luna/feed/radio/tracks`)是**真拿不到 50**: 每次固定 6 首, `count`/`limit`/
#      `cursor`/`offset` 全部无效; 电台 id 也不是 playlist id(`playlist/detail` 回
#      `1000005`), 且无 `/luna/radio/detail` 一类端点(404)。故电台改为多轮累积去重
#      (上限 6 轮 ≈ 3.5s, 通常 20 首左右), 这是服务端限制, 非源侧可解。
#   ⚠️ TVBox 的**详情页没有分页**(一次返回全部集数), 做不到官方那种「查看更多继续加载」,
#      所以这里一次给足: extend 的 `mode_count`(默认 50, 上限 200) 控制条数。
#   ⚠️ 偏好模式的 `mode`(default/familiar/fresh) 参数**对未登录请求不生效**(同参数连调
#      3 次结果全不同, 三个 mode 间也无稳定差异 —— 服务端个性化需要登录态)。故「默认/
#      熟悉/新鲜」三个模式拿到的是同一个官方随机推荐池; 参数照传, 源侧无法进一步区分。
#   改动: 1) 新增 `_mode_playlists()` / `_feed_mode_tracks()`(走官方 discover/mix 的
#            推荐歌单池 → playlist/detail 展开);
#         2) `kind="preference"` / `"scene"` 改走 `_feed_mode_tracks()`, **删掉**「热歌榜/
#            新歌榜/怀旧电台顶替」与「按模式名搜索」两条兜底(怀旧电台仅留作 familiar 的
#            最终兜底);
#         3) `_radio_tracks(radio_id, want)` 增加多轮累积去重;
#         4) 新增 `mode_count` 开关与 `_mode_want()`; 新增 `_MODE_TRACK_CACHE`(600s 缓存,
#            推荐池是随机采样, 不缓存会让详情页每次结果都变)。
#
# 开关(写在源配置的 extend 里, 均为可选):
#   "proxy":1         启用本地音频代理(实验性! 输出 127.0.0.1 地址, 多数播放器不支持,
#                     实测会导致整条线路无声; 仅在确认播放器能播 loopback 时才开)
#   "music_player":0  去掉 music_player 标记(默认 1, 与原版一致)
#   "app_probe":1     打开官方流的地址探测(★默认 0=关闭)。关闭时直接给 seo 的 main_url,
#                     **逐字节等同于原版行为**; 打开会按 Content-Type=audio/* 且真能取到
#                     字节来挑候选, 但起播会多 0.6~1.1s。仅用于对照排查。
#   "prefetch":0      关闭详情页后台预热(默认开; 关掉后首次播放按需解析, 会慢 ~0.2s)
#   "audio_format":1  回填 format=音频 MIME(★默认 0=不回填)。它在**非沉浸式**下会命中
#                     `AudioUtil.isAudio()` 判据①把官方档位分流到 AudioActivity; 沉浸式
#                     (默认)下不生效。保留仅为对照排查。
#   "mode_count":100  听歌模式/电台一次返回的曲目条数(★默认 50, 范围 20~200)。
#                     TVBox 详情页不能翻页, 只能靠调大这个值来「加载更多」。
#
# 格式约定: vod_play_from 用 $$$ 分隔线路; vod_play_url 同序;
#           集内 # 分隔; 每集 title$id 用 $ 分隔。
import base64
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import requests
except Exception:
    requests = None

try:
    from base.spider import Spider as BaseSpider
except Exception:
    class BaseSpider(object):
        pass

API = "https://api.qishui.com"
UA = ("Mozilla/5.0 (Linux; Android 12; TVBox) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
ICON = ("https://is1-ssl.mzstatic.com/image/thumb/Purple211/v4/23/19/5a/"
        "23195ac8-3fbf-d33b-16ed-20854f9afd35/"
        "AppIcon-0-0-1x_U007epad-0-1-0-85-220.png/512x512bb.jpg")

# 热歌榜 / 新歌榜(实测可用)
CHARTS = [("热歌榜", "7036274230471712007"), ("新歌榜", "7060812597884869927")]
# 官方档位 → audio/mp4 候选地址的探测结果缓存 {(track_id, quality): (url, ts)}
# URL 有效期约 1 天, 缓存只保 300s, 避免过期地址被复用。
_APP_PROBE_CACHE = {}
# 听歌模式曲目缓存 {"s:<scene_id>|m:<mode>|<want>": (tracks, ts)}。
# 模式流是服务端**随机推荐**, 同一模式连续请求结果不同; 缓存 600s 免得详情页反复拉取。
_MODE_TRACK_CACHE = {}
_MODE_TRACK_TTL = 600

# ---------------------------------------------------------------- 完整音源(酷我直连)
# 「VIP替代」线原本走第三方聚合站(yx520), 单次冷启 2.4s / 热 1s → 起播慢。
# 实测: 酷我官方接口「搜索 + 取流」合计只要 0.1~0.2s, 且拿到的 320k mp3 与聚合站是
# **同一份文件**(字节数完全一致) → 直接打酷我, 起播快 10 倍以上。
#   ① 搜索 https://search.kuwo.cn/r.s?client=kt&all=<歌名 歌手>&ft=music&rformat=json&mobi=1
#   ② 取流 https://nmobi.kuwo.cn/mobi.s?type=convert_url_with_sign&rid=<rid>&br=320kmp3&format=mp3
# ★参数坑: 高码率必须用 `br=320kmp3`(名字里带单位), 用 `bitrate=320kmp3` 只会给 128k。
#   另有无损档 `br=2000kflac`(format=flac, ~26MB), 默不启用。
# 聚合站(yx520)保留为兜底: 酷我直连失败时才用。
_KUWO_SEARCH = "https://search.kuwo.cn/r.s"
_KUWO_SIGN = "https://nmobi.kuwo.cn/mobi.s"
_KUWO_SOURCE = "kwplayer_ar_4.4.2.7_B_nuoweida_vh.apk"
# 结果缓存 "歌名|歌手" → {"url","ext","ts"}。酷我直连 token 会过期, 故给 TTL。
_ALT_CACHE = {}
_ALT_LOCK = threading.Lock()
_ALT_FRESH = 900         # 900s 内直接复用(重解析只要 0.15s, 故无需更长的无校验窗口)
_ALT_TTL = 6 * 3600      # 超过 6h 直接丢弃
# 详情页后台预热: 打开详情时把「VIP替代」的直链先解析好, 用户点播放即秒开。
_PREFETCH_LOCK = threading.Lock()
_PREFETCH_DONE = set()
_PREFETCH_MAX = 3        # 合集最多预热前 N 首(避免同时打太多请求)
# 匹配打分: 命中这些修饰词的版本重罚(伴奏/翻唱/Live/epic 等短版或改编版), 优先原版。
# ★实测: 「孤勇者(热血epic版)」只有 48 秒; 不重罚这类词就会选中短版当原版。
# 中文词用子串判定; 英文词必须独立成词(否则 "inst" 会误伤 "Instinct" 这类正常曲名)。
_ALT_NOISE_CJK = ("伴奏", "纯音乐", "铃声", "翻唱", "改编", "串烧", "合唱", "对唱", "童声",
                  "钢琴", "吉他", "唢呐", "二胡", "环绕", "现场", "摇滚", "慢摇", "片段",
                  "试听", "演唱会", "巡演", "音乐节", "原曲", "旧版")
_ALT_NOISE_EN = ("dj", "remix", "live", "cover", "inst", "epic", "demo", "remaster", "ktv", "3d")
# 怀旧电台: 仅作「熟悉模式」的**最终兜底** —— 主路径已改用官方 discover/mix
# (见文件头「第十一轮」); 电台接口每次只回 6 首且无分页参数, 不适合当主数据源。
NOSTALGIA_RADIO = "7408841207276748809"
# 听抖音分类: (显示名, 搜索关键词)。★关键词用分类名本身; 不要用「热门视频」。
VIDEO_CATS = [
    ("推荐", "推荐"), ("音乐", "音乐"), ("助眠", "助眠"), ("脱口秀", "脱口秀"),
    ("相声", "相声"), ("影视解说", "影视解说"), ("历史", "历史"), ("科普", "科普"),
    ("财经", "财经"), ("职场", "职场"), ("悬疑", "悬疑"), ("小说", "小说"),
    ("爽文", "爽文"), ("现言", "现言"), ("穿越", "穿越"), ("重生", "重生"),
    ("脑洞", "脑洞"), ("男频", "男频"), ("女频", "女频"), ("社会时政", "社会时政"),
]
# 模式墙排序(接口返回顺序不稳定, 按此表归一; 表外模式排最后)
MODE_ORDER = [
    "默认模式", "熟悉模式", "新鲜模式", "图书馆", "专注模式", "摸鱼", "深夜emo", "dj模式", "助眠模式",
    "动感健身", "抖音漫游", "洗澡", "chill放松", "快乐时光", "电音", "好运", "粤语", "通勤必听",
    "失恋必听", "躺平", "欧美", "打扫", "国风", "打游戏", "驾车", "说唱", "沉浸0.8x", "夜晚",
    "治愈", "轻音乐", "小酒馆", "ktv必点", "起床", "浪漫情歌", "摇滚", "r&b", "佛系时间",
    "怀旧老歌", "民谣", "甜美女声", "k-pop", "日语", "旅行", "儿歌", "雨天", "海边", "乡村", "古典",
]


# ====================================================================== 本地音频代理
# 目的: 把上游音频地址包装成本机地址, 修正 Content-Type 与文件后缀, 解决 Exo「能播没声音」。
#   上游: Content-Type=video/mp4 + URL 无后缀  →  本地: audio/mp4 + /audio/<token>.m4a
# 实现: 127.0.0.1 上起一个透传 HTTP 服务, 原样转发 Range, 返回时改写 Content-Type。
# 端口: 10010 起顺序探测(避开红果短剧占用的 9990-9999)。
_STREAM_LOCK = threading.Lock()
_STREAM_STATE = {"port": 0, "server": None, "urls": {}}
_STREAM_PORT_RANGE = (10010, 10110)
_STREAM_TIMEOUT = 30
_STREAM_CHUNK = 65536
# 后缀 → Content-Type(音频)。未知后缀默认 audio/mp4(官方 M4A 容器)。
_CTYPE = {
    ".m4a": "audio/mp4", ".mp4": "audio/mp4", ".mp3": "audio/mpeg",
    ".aac": "audio/aac", ".flac": "audio/flac", ".wav": "audio/wav", ".ogg": "audio/ogg",
}
_URL_EXTS = (".m4a", ".mp3", ".flac", ".aac", ".wav", ".ogg", ".mp4")


def _ext_of(url, fallback=".m4a"):
    """优先按 URL 后缀定后缀; 无后缀则用 fallback(.m4a=官方 M4A 容器)。"""
    path = str(url or "").split("?")[0].lower()
    for ext in _URL_EXTS:
        if path.endswith(ext):
            return ext
    return fallback


def _uniq(seq):
    """去重且保持原顺序, 顺手丢掉空值。

    用途: seo 的 main_url / backup_url 经常是同一条 URL 的两个副本, 不去重会把
    同一个地址 HEAD 探测两遍(`_head_is_audio` 要发 1 次 HEAD + 1 次 Range GET,
    重复探测纯属浪费, 在设备上还会拖慢起播)。
    """
    out, seen = [], set()
    for item in seq or ():
        key = str(item or "")
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _register(url):
    """登记上游地址 → 返回稳定 token(同地址同 token, HEAD/GET 一致)。"""
    token = hashlib.md5(str(url).encode("utf-8")).hexdigest()[:16]
    with _STREAM_LOCK:
        _STREAM_STATE["urls"][token] = str(url)
    return token


def _start_audio_server():
    with _STREAM_LOCK:
        if _STREAM_STATE["port"]:
            return int(_STREAM_STATE["port"])
        for port in range(_STREAM_PORT_RANGE[0], _STREAM_PORT_RANGE[1]):
            try:
                server = ThreadingHTTPServer(("127.0.0.1", port), _AudioHandler)
            except OSError:
                continue
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            _STREAM_STATE["port"] = port
            _STREAM_STATE["server"] = server
            return port
    return 0


def _proxy_url(url, ext=None):
    """把上游音频地址包装成本机代理地址; 起不来服务则原样返回(不阻断播放)。"""
    url = str(url or "")
    if not url:
        return url
    port = _start_audio_server()
    if not port:
        return url
    return "http://127.0.0.1:%d/audio/%s%s" % (port, _register(url), ext or _ext_of(url))


def _upstream_headers(range_value=""):
    headers = {"User-Agent": UA, "Referer": "https://music.douyin.com/", "Accept": "*/*"}
    if range_value:
        headers["Range"] = range_value
    return headers


class _AudioHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "qishui-audio"

    def log_message(self, *args):
        return None

    def do_HEAD(self):  # noqa: N802 - 标准库回调命名
        self._serve(False)

    def do_GET(self):  # noqa: N802 - 标准库回调命名
        self._serve(True)

    def _fail(self, code, message=b""):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(message)))
        self.send_header("Connection", "close")
        self.end_headers()
        if message:
            try:
                self.wfile.write(message)
            except OSError:
                pass

    def _serve(self, body):
        name = urllib.parse.urlparse(self.path).path.rsplit("/", 1)[-1]
        token, _, ext = name.partition(".")
        url = _STREAM_STATE["urls"].get(token) if token else None
        if not url:
            self._fail(404, b"not found")
            return
        ctype = _CTYPE.get("." + ext.lower(), "audio/mp4") if ext else "audio/mp4"
        raw_range = self.headers.get("Range") or ""
        try:
            resp = urllib.request.urlopen(
                urllib.request.Request(url, headers=_upstream_headers(raw_range)), timeout=_STREAM_TIMEOUT)
        except urllib.error.HTTPError as exc:
            # 上游 416(Range 越界)原样透传, 让播放器自己纠正; 其它错误给 502
            code = int(getattr(exc, "code", 502) or 502)
            if code == 416:
                content_range = exc.headers.get("Content-Range") if getattr(exc, "headers", None) else None
                self.send_response(416)
                self.send_header("Content-Type", ctype)
                self.send_header("Accept-Ranges", "bytes")
                if content_range:
                    self.send_header("Content-Range", content_range)
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()
                try:
                    exc.close()
                except Exception:
                    pass
                return
            self._fail(502, b"upstream %d" % code)
            return
        except Exception:
            self._fail(502, b"upstream failed")
            return
        try:
            status = int(getattr(resp, "status", 200) or 200)
            if status not in (200, 206):
                status = 200
            total = int(resp.headers.get("Content-Length") or 0)
            content_range = resp.headers.get("Content-Range")
            self.send_response(status)
            self.send_header("Content-Type", ctype)      # ★ 关键: 上游是 video/mp4, 这里纠正为音频
            self.send_header("Accept-Ranges", "bytes")
            if content_range:
                self.send_header("Content-Range", content_range)
            if total:
                self.send_header("Content-Length", str(total))
            self.send_header("Connection", "close")
            self.end_headers()
            if not body:
                return
            while True:
                chunk = resp.read(_STREAM_CHUNK)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:
            self.close_connection = True
        finally:
            try:
                resp.close()
            except Exception:
                pass


class Spider(BaseSpider):
    def __init__(self):
        self._sess = None
        self._kuwo_sess = None
        self._cfg = {}

    def init(self, extend=""):
        try:
            self._cfg = json.loads(extend) if (isinstance(extend, str) and extend.strip()) else extend
        except Exception:
            self._cfg = {}
        if not isinstance(self._cfg, dict):
            self._cfg = {}

    def getName(self):
        return "汽水音乐"

    # ------------------------------------------------------------------ HTTP
    def _session(self):
        if self._sess is None:
            s = requests.Session()
            s.headers.update({
                "User-Agent": UA,
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://music.douyin.com/",
            })
            self._sess = s
        return self._sess

    def _req(self, path, body=None, query=None):
        """统一请求: GET(query) / POST(body) 都返回 dict, 失败返回 {}"""
        if requests is None:
            return {}
        url = API + path
        try:
            if body is None:
                r = self._session().get(url, params=query or None, timeout=18)
            else:
                r = self._session().post(
                    url, params=query or None,
                    data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                    headers={"Content-Type": "application/json; charset=utf-8"}, timeout=18)
            data = r.json()
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------- 字段工具
    @staticmethod
    def _first(value):
        return value[0] if isinstance(value, list) and value else value

    @classmethod
    def _img(cls, image):
        """封面: urls 里形如 https://p3-luna.douyinpic.com/img/ 需拼 uri + 模板后缀"""
        if not isinstance(image, dict):
            return ""
        uri = str(image.get("uri") or "")
        url = str(cls._first(image.get("urls")) or "")
        if url and url.rstrip("/").endswith("/img"):
            if not uri:
                return ""
            full = url.rstrip("/") + "/" + uri.lstrip("/")
            tpl = str(image.get("template_prefix") or "")
            return full + ("~" + tpl + "-ori.image" if tpl else "")
        return url or uri

    @staticmethod
    def _pack(kind, value):
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return kind + ":" + base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    @staticmethod
    def _unpack(value, kind):
        text = str(value or "")
        prefix = kind + ":"
        if not text.startswith(prefix):
            return None
        raw = text[len(prefix):]
        try:
            return json.loads(base64.urlsafe_b64decode((raw + "=" * (-len(raw) % 4)).encode()).decode())
        except Exception:
            return None

    @staticmethod
    def _result(items, page=1, more=False, size=20):
        page = max(1, int(page or 1))
        return {
            "list": items, "page": page,
            "pagecount": page + 1 if more else page,
            "limit": size,
            "total": (page - 1) * size + len(items) + (size if more else 0),
        }

    @staticmethod
    def _extend(extend, key, default=""):
        value = extend.get(key, default) if isinstance(extend, dict) else default
        if isinstance(value, list):
            value = value[0] if value else default
        if isinstance(value, dict):
            value = value.get("v") or value.get("value") or default
        return str(value if value not in (None, "") else default)

    @staticmethod
    def _track(obj):
        """从各种嵌套结构里抠出 track 对象"""
        if not isinstance(obj, dict):
            return None
        if obj.get("id") and (obj.get("name") or obj.get("title")):
            return obj
        for path in (("track",), ("track_wrapper", "track"),
                     ("entity", "track_wrapper", "track"), ("entity", "track")):
            value = obj
            for key in path:
                value = value.get(key) if isinstance(value, dict) else None
            if isinstance(value, dict) and value.get("id"):
                return value
        return None

    @staticmethod
    def _artists(track):
        return " / ".join(str(a.get("name") or "") for a in (track.get("artists") or [])
                          if isinstance(a, dict) and a.get("name"))

    @classmethod
    def _card(cls, track):
        """track → TVBox 卡片"""
        if not isinstance(track, dict) or not track.get("id"):
            return None
        artists = cls._artists(track)
        album = track.get("album") if isinstance(track.get("album"), dict) else {}
        remark = artists or str(album.get("name") or "汽水音乐")
        return {
            "vod_id": cls._pack("t", str(track["id"])),
            "vod_name": str(track.get("name") or "未知歌曲"),
            "vod_pic": cls._img(album.get("url_cover") or track.get("url_cover") or {}),
            "vod_remarks": remark[:60],
        }

    # ------------------------------------------------------------------ 分类
    def homeContent(self, filter):
        classes = [
            {"type_id": "mode", "type_name": "听歌模式"},
            {"type_id": "discover", "type_name": "发现"},
            {"type_id": "chart", "type_name": "榜单"},
            {"type_id": "listen_video", "type_name": "听抖音"},
        ]
        filters = {
            "listen_video": [{"key": "cate", "name": "分类",
                              "value": [{"n": n, "v": v} for n, v in VIDEO_CATS]}],
        }
        return {"class": classes, "filters": filters}

    def homeVideoContent(self):
        try:
            return self._modes(1)
        except Exception:
            return self._result([], 1)

    def categoryContent(self, tid, pg, filter, extend):
        page = max(1, int(pg or 1))
        try:
            if str(tid) == "mode":
                return self._modes(page)
            if str(tid) == "discover":
                return self._discover(page)
            if str(tid) == "chart":
                return self._charts(page)
            return self._listen(self._extend(extend, "cate", "推荐"), page)
        except Exception:
            return self._result([], page)

    def _modes(self, page):
        """听歌模式墙(3 个基础偏好 + 接口返回的场景模式)"""
        data = self._req("/luna/feed/mode", {"ab_param": "", "feed_extra": None})
        modes = [
            {"id": "default", "name": "默认模式", "kind": "preference"},
            {"id": "familiar", "name": "熟悉模式", "kind": "preference"},
            {"id": "fresh", "name": "新鲜模式", "kind": "preference"},
        ]
        for group in (data.get("feed_mode_block") or []):
            for mode in (group.get("feed_mode") or []):
                scene = ((mode.get("entity") or {}).get("feed_scene_mode") or {})
                sid = str(scene.get("scene_mode_id") or mode.get("text") or "")
                if sid:
                    modes.append({"id": sid, "name": str(mode.get("text") or "听歌模式"), "kind": "scene"})
        cards, seen = [], set()
        for info in modes:
            key = info["name"].lower().replace(" ", "")
            if not info["id"] or key in seen:
                continue
            seen.add(key)
            cards.append({"vod_id": self._pack("m", info), "vod_name": info["name"],
                          "vod_pic": ICON, "vod_remarks": "听歌模式"})
        order = {n.lower().replace(" ", ""): i for i, n in enumerate(MODE_ORDER)}
        cards.sort(key=lambda x: order.get(x["vod_name"].lower().replace(" ", ""), len(order)))
        return self._result(cards, page, False, max(1, len(cards)))

    def _discover(self, page):
        """发现页: blocks + 混合流"""
        data = self._req("/luna/discover", {
            "ab_param": "", "selected_boost": None, "playlist_mix_param": None,
            "feed_discover_extra": None, "first_request": True})
        blocks = list(data.get("blocks") or [])
        for _ in range(2):
            mixed = self._req("/luna/discover/mix", {
                "block_type": "discover_playlist_mix", "sub_channel_id": 0,
                "latest_douyin_liked_playlist_show_ts": None, "feed_discover_extra": {},
                "cursor": None, "count": 50, "session_id": None, "ab_param": ""})
            blocks.append({"inner_block": mixed.get("inner_block") or [], "title": "发现"})
        cards, seen = [], set()
        for block in blocks:
            inners = block.get("inner_block") or ([block] if block.get("resources") else [])
            for inner in inners:
                for res in (inner.get("resources") or []):
                    kind = str(res.get("type") or "radio")
                    rid = str(res.get("resource_id") or "")
                    if not rid or (kind, rid) in seen:
                        continue
                    seen.add((kind, rid))
                    style = res.get("style") if isinstance(res.get("style"), dict) else {}
                    entity = res.get("entity") if isinstance(res.get("entity"), dict) else {}
                    cover = style.get("cover_url") or self._first(style.get("cover_url_list")) or {}
                    if not cover and isinstance(entity.get("playlist"), dict):
                        cover = entity["playlist"].get("url_cover") or {}
                    name = str(style.get("title") or inner.get("title") or "发现")
                    desc = str(style.get("desc") or block.get("title") or "发现")
                    cards.append({
                        "vod_id": self._pack("c", {"id": rid, "kind": kind, "name": name, "desc": desc,
                                                   "pic": self._img(cover)}),
                        "vod_name": name, "vod_pic": self._img(cover), "vod_remarks": desc[:60]})
        return self._result(cards, page, False, max(1, len(cards)))

    def _charts(self, page):
        return self._result([
            {"vod_id": self._pack("c", {"id": cid, "kind": "chart", "name": name,
                                        "desc": "榜单", "pic": ICON}),
             "vod_name": name, "vod_pic": ICON, "vod_remarks": "榜单"}
            for name, cid in CHARTS], page, False, len(CHARTS))

    def _listen(self, cate, page):
        """听抖音视频流"""
        name = next((n for n, v in VIDEO_CATS if v == str(cate)), str(cate) or "推荐")
        keyword = name or "推荐"
        payload = {
            "search_type": "listen_video", "q": keyword,
            "cursor": None if page == 1 else str((page - 1) * 20),
            "search_id": keyword, "search_method": "input",
            "search_scene": "search_result", "scene_name": "listen_video",
        }
        data = self._req("/luna/search/listen_video", payload, {"device_platform": "web"})
        group = next((g for g in (data.get("result_groups") or []) if g.get("id") == "listen_video"), {})
        cards = []
        for item in (group.get("data") or []):
            video = ((item.get("entity") or {}).get("video") or {})
            vid = str(video.get("vid") or "")
            if not vid:
                continue
            title = str(video.get("title") or video.get("description") or "听抖音")
            cover = self._img(video.get("cover_url") or video.get("image_url") or {})
            dur = int(video.get("duration") or 0) // 1000
            cards.append({
                "vod_id": self._pack("v", {"vid": vid, "name": title, "pic": cover, "dur": dur}),
                "vod_name": title, "vod_pic": cover,
                "vod_remarks": "%d:%02d" % (dur // 60, dur % 60) if dur else "听抖音"})
        return self._result(cards, page, bool(group.get("has_more")), 20)

    # ------------------------------------------------------------------ 搜索
    def searchContent(self, key, quick=False, pg="1"):
        return self.searchContentPage(key, quick, pg)

    def searchContentPage(self, key, quick=False, pg="1"):
        page = max(1, int(pg or 1))
        keyword = str(key or "").strip()
        if not keyword:
            return self._result([], 1)
        payload = {
            "search_type": "track", "q": keyword,
            "cursor": None if page == 1 else str((page - 1) * 20),
            "search_id": keyword, "search_method": "input", "search_scene": "search_result",
        }
        try:
            data = self._req("/luna/search/track", payload, {"device_platform": "web"})
            group = next((g for g in (data.get("result_groups") or []) if g.get("id") == "tracks"), {})
            cards = [c for c in (self._card(self._track(x)) for x in (group.get("data") or [])) if c]
            return self._result(cards, page, bool(group.get("has_more")), 20)
        except Exception:
            return self._result([], page)

    # ------------------------------------------------------------------ 详情
    def detailContent(self, ids):
        value = str(ids[0] if isinstance(ids, (list, tuple)) else ids)
        try:
            video = self._unpack(value, "v")
            if video:
                return {"list": [self._video_detail(video)], "parse": 0, "jx": 0}
            collection = self._unpack(value, "c")
            if collection:
                return {"list": [self._collection_detail(collection)], "parse": 0, "jx": 0}
            mode = self._unpack(value, "m")
            if mode:
                return {"list": [self._collection_detail(mode)], "parse": 0, "jx": 0}
            track = self._unpack(value, "t")
            return {"list": [self._track_detail(track or value)], "parse": 0, "jx": 0}
        except Exception:
            return {"list": [{"vod_id": value, "vod_name": "汽水音乐", "vod_play_from": "汽水音乐",
                              "vod_play_url": "播放$a:" + value + ":auto"}], "parse": 0, "jx": 0}

    def _seo(self, track_id):
        return self._req("/luna/h5/seo_track", None,
                         {"track_id": str(track_id), "device_platform": "web"})

    def _req_url(self, url):
        if requests is None:
            return {}
        try:
            return self._session().get(url, timeout=18).json()
        except Exception:
            return {}

    # --------------------------------------------------- VIP/试听歌曲替代
    # 汽水对会员曲只放「试听片段」: video_list 只 1 档, 且正片短。判定依据
    # (实测 2026-10-13): seo_track.track.label_info.only_vip_playable = true
    # 或 track.audition_info 非空。命中后改走 yx520 的完整音源兜底:
    #   ① 酷我 kwyy → 返回 kuwo mp3 直链(完整, ~10MB, audio/mpeg)
    #   ② 抖音 dyyy → 返回 douyin audio_mp4 直链(完整, ~7MB)
    # 两个都是第三方免费接口, 任一可用即可; 全挂则回落官方试听档, 不阻断播放。
    @staticmethod
    def _clip_seconds(streams):
        """估算官方流实际时长(秒)。用最高档的 size/bitrate 反推; 拿不到返回 0。"""
        if not streams:
            return 0.0
        top = max(streams, key=lambda s: s.get("bitrate") or 0)
        bitrate = float(top.get("bitrate") or 0)
        size = float(top.get("size") or 0)
        if bitrate <= 0 or size <= 0:
            return 0.0
        return size * 8.0 / bitrate

    def _is_vip(self, data, streams=None):
        """会员/试听曲判定 → 决定是否需要第三方替代源拿完整曲。

        ★判据是「官方流实际时长 vs 曲目完整时长」: 官方对会员/版权曲只放片段(实测 30s/60s),
        故 est < full*0.8 即判为片段。不能只看 audition_info —— 实测存在「带 audition_info
        但官方流是完整曲」的情况(稻香 269.6s), 只看它会误判并把完整曲也改走替代源。
        size/bitrate 拿不到时才退回 label_info.only_vip_playable。
        """
        track = self._track((data or {}).get("seo_track") or {}) or {}
        label = track.get("label_info") if isinstance(track.get("label_info"), dict) else {}
        full = int(track.get("duration") or 0) / 1000.0
        est = self._clip_seconds(streams or [])
        if est > 0 and full > 0:
            return est < full * 0.8
        return bool(label.get("only_vip_playable"))

    # ------------------------------------------------- 完整音源: 酷我直连(快) → 聚合站(兜底)
    def _kuwo_session(self):
        if self._kuwo_sess is None:
            s = requests.Session()
            s.headers.update({"User-Agent": UA, "Referer": "https://www.kuwo.cn/"})
            self._kuwo_sess = s
        return self._kuwo_sess

    @staticmethod
    def _norm_text(text, keep_brackets=False):
        """归一化曲名/歌手用于比对: 去标点空白 + 小写; 默认再去括号内容。

        keep_brackets=True 时保留括号内容 —— 打分必须用它, 否则「孤勇者(热血epic版)」
        去括号后会与「孤勇者」完全相等, 版本信息被抹掉, 假原版拿满分(实测踩过)。
        """
        t = str(text or "").lower()
        if not keep_brackets:
            t = re.sub(r"[（(\[【].*?[)）\]】]", "", t)
        t = re.sub(r"[\s\-—_·、,，.。!！?？'\"“”~:：]+", "", t)
        return t.strip()

    @staticmethod
    def _alt_score(item, name, artist):
        """给酷我搜索结果打分; 名字对不上直接判不可用(-1)。

        ★核心是「去掉标题后还剩多少字符」(extra) —— 越接近纯标题越像原版。
        实测教训: 改用此判据前, 搜「孤勇者」会选中「孤勇者(热血epic版)」(48 秒短版),
        而真原版「孤勇者-《英雄联盟…》主题曲」和排第 9 的纯「孤勇者」都落选。
        """
        raw = str(item.get("SONGNAME") or "")
        flat = Spider._norm_text(raw, keep_brackets=True)
        target = Spider._norm_text(name)
        if not flat or not target or target not in flat:
            return -1
        extra = len(flat.replace(target, "", 1))
        score = 100 - min(extra, 30) * 3          # 多余字符越多越不像原版
        low = raw.lower()
        if any(bad in low for bad in _ALT_NOISE_CJK) or any(
                re.search(r"(?<![a-z0-9])" + re.escape(bad) + r"(?![a-z0-9])", low)
                for bad in _ALT_NOISE_EN):
            score -= 45                           # 伴奏/翻唱/Live/epic/片段 等版本重罚
        if artist:
            mine = [Spider._norm_text(x) for x in re.split(r"[/&、,，]", artist)]
            mine = [x for x in mine if x]
            theirs = Spider._norm_text(item.get("ARTIST"))
            if mine and theirs:
                if any(x in theirs or theirs in x for x in mine):
                    score += 40
                else:
                    score -= 25
        return score

    def _kuwo_search(self, keyword, rn=10):
        url = ("%s?client=kt&pn=0&rn=%d&all=%s&vipver=1&ft=music&encoding=utf8&rformat=json&mobi=1"
               % (_KUWO_SEARCH, rn, urllib.parse.quote(keyword)))
        try:
            resp = self._kuwo_session().get(url, timeout=8)
            try:
                data = resp.json()
            except Exception:
                data = json.loads(resp.text.replace("'", '"'))
            return data.get("abslist") or []
        except Exception:
            return []

    def _kuwo_rid(self, name, artist):
        """搜出最匹配的酷我 rid: 先用「歌名 歌手」, 没好的再退化到只用「歌名」。"""
        first_artist = re.split(r"[/&、,，]", artist or "")[0].strip()
        queries = ([name + " " + first_artist] if first_artist else []) + [name]
        best, best_score, seen = "", -1, set()
        for keyword in queries:
            for pos, item in enumerate(self._kuwo_search(keyword)):
                rid = str(item.get("DC_TARGETID") or item.get("MUSICRID") or "").replace("MUSIC_", "").strip()
                if not rid or rid in seen:
                    continue
                seen.add(rid)
                score = self._alt_score(item, name, artist)
                if score < 0:
                    continue
                score -= pos * 2              # 同分时尊重酷我原排序(靠前的更可能是原版)
                if score > best_score:
                    best, best_score = rid, score
            if best and best_score >= 55:
                break
        if not best:                          # 打分全军覆没 → 退化为只用歌名搜的第一条
            for item in self._kuwo_search(name):
                rid = str(item.get("DC_TARGETID") or item.get("MUSICRID") or "").replace("MUSIC_", "").strip()
                if rid:
                    return rid
        return best

    def _kuwo_url(self, name, artist, br="320kmp3", fmt="mp3"):
        """酷我直连取流: 搜索 → convert_url_with_sign, 实测全程 0.1~0.2s。"""
        rid = self._kuwo_rid(name, artist)
        if not rid:
            return "", ""
        url = ("%s?f=web&user=0&source=%s&type=convert_url_with_sign&rid=%s&br=%s&format=%s"
               % (_KUWO_SIGN, _KUWO_SOURCE, rid, br, fmt))
        try:
            link = str((((self._kuwo_session().get(url, timeout=8).json()).get("data") or {}).get("url")) or "")
        except Exception:
            link = ""
        if link.startswith("http"):
            return link, _ext_of(link, "." + fmt)
        return "", ""

    def _yx520_url(self, name):
        """聚合站兜底(冷启 ~2.4s, 慢): 只在酷我直连失败时用。"""
        q = urllib.parse.quote(name)
        try:
            j = self._req_url("http://www.yx520.ltd/API/kwyy/api.php?msg=%s&a=10&n=1" % q)
            if str(j.get("code")) == "200" and j.get("url"):
                url = str(j["url"])
                return url, _ext_of(url, ".mp3")
        except Exception:
            pass
        try:
            j = self._req_url("http://www.yx520.ltd/API/dyyy/api.php?msg=%s" % q)
            items = j.get("data") or []
            if items:
                hit = next((x for x in items if name in str(x.get("title") or "")), items[0])
                if hit.get("url"):
                    url = str(hit["url"])
                    return url, _ext_of(url, ".m4a")
        except Exception:
            pass
        return "", ""

    def _alt_url(self, name, artist=""):
        """第三方完整音源: 酷我直连(0.1~0.2s) 优先 → 聚合站 yx520 兜底; 取不到返回 ('', '')。

        返回 (url, ext), ext 供本地代理判定 Content-Type(.mp3 / .m4a)。
        带内存缓存(900s 内直接复用) → 同一首重播/连续播放时零网络等待。
        """
        name = str(name or "").strip()
        if not name:
            return "", ""
        artist = str(artist or "").strip()
        key = name.lower() + "|" + artist.lower()
        now = time.time()
        with _ALT_LOCK:
            hit = _ALT_CACHE.get(key)
        if hit and now - hit["ts"] < _ALT_FRESH:
            return hit["url"], hit["ext"]                 # 900s 内直接复用, 播放秒开
        url, ext = self._kuwo_url(name, artist)
        if not url:
            url, ext = self._yx520_url(name)
        if not url and hit and now - hit["ts"] < _ALT_TTL:
            return hit["url"], hit["ext"]                 # 重解析失败 → 保留旧地址兜底
        if url:
            with _ALT_LOCK:
                _ALT_CACHE[key] = {"url": url, "ext": ext, "ts": time.time()}
                if len(_ALT_CACHE) > 400:                 # 简单 LRU 清理, 防无界增长
                    for k in sorted(_ALT_CACHE, key=lambda x: _ALT_CACHE[x]["ts"])[:100]:
                        _ALT_CACHE.pop(k, None)
        return url, ext

    def _prefetch_alt(self, values):
        """详情页后台预热「完整音源」直链(不阻塞详情返回)。

        用户点开详情后通常还要 1s 以上才按播放, 预热完即命中缓存 → 点下去立刻出声。
        """
        if not self._flag("prefetch", True):
            return
        jobs = []
        for value in values:
            info = self._unpack(value, "m")
            if isinstance(info, dict) and info.get("n"):
                jobs.append((str(info["n"]), str(info.get("r") or "")))
        if not jobs:
            return
        jobs = jobs[:_PREFETCH_MAX]

        def run():
            for n, r in jobs:
                key = n.lower() + "|" + r.lower()
                with _PREFETCH_LOCK:
                    if key in _PREFETCH_DONE:
                        continue
                    if len(_PREFETCH_DONE) > 500:
                        _PREFETCH_DONE.clear()
                    _PREFETCH_DONE.add(key)
                try:
                    self._alt_url(n, r)
                except Exception:
                    pass

        threading.Thread(target=run, daemon=True).start()

    @staticmethod
    def _label(quality, bitrate, index):
        q = str(quality or "").lower()
        name = {"lossless": "无损", "highest": "极高", "higher": "较高",
                "medium": "标准", "low": "省流"}.get(q)
        kbps = max(0, int(bitrate or 0) // 1000)
        if name:
            return "%s音质(%dK)" % (name, kbps) if kbps else name + "音质"
        return "%dKbps" % kbps if kbps else "音质%d" % (index + 1)

    def _streams(self, data):
        """从 seo_track 结果解析音质档位, 按码率降序返回 [{key,label,bitrate,url}]"""
        player = data.get("track_player") if isinstance(data.get("track_player"), dict) else {}
        model = player.get("video_model")
        if isinstance(model, str) and model:
            try:
                model = json.loads(model)
            except Exception:
                model = {}
        out = []
        for idx, item in enumerate((model or {}).get("video_list") or []):
            if not isinstance(item, dict) or item.get("encrypt_info"):
                continue  # 加密流跳过
            meta = item.get("video_meta") or {}
            url = item.get("main_url") or item.get("backup_url")
            if not url:
                continue
            quality = str(meta.get("quality") or idx)
            out.append({"key": quality, "label": self._label(quality, meta.get("bitrate"), idx),
                        "bitrate": int(meta.get("bitrate") or 0), "size": int(meta.get("size") or 0),
                        "url": str(url)})
        if not out and player.get("url_player_info"):
            box = ((self._req_url(str(player["url_player_info"])).get("Result") or {}).get("Data") or {})
            for idx, item in enumerate(box.get("PlayInfoList") or []):
                url = item.get("MainPlayUrl") or item.get("BackupPlayUrl")
                if url:
                    quality = str(item.get("Quality") or idx)
                    out.append({"key": quality, "label": self._label(quality, item.get("Bitrate"), idx),
                                "bitrate": int(item.get("Bitrate") or 0),
                                "size": int(item.get("Size") or item.get("SizeBytes") or 0),
                                "url": str(url)})
        uniq = {}
        for s in out:
            uniq[(s["key"], s["bitrate"])] = s
        return sorted(uniq.values(), key=lambda x: x["bitrate"], reverse=True)

    # --------------------------------------- 官方(App)流: 挑 audio/mp4 的候选地址
    # ★实测(2026-10-13)关键规律:
    #   1) 官方音频是 audio-only 的 M4A(media_type=audio / vtype=m4a), CDN 在
    #      /video/tos/... 路径下分发, **响应头 Content-Type 会因 CDN 节点而异**:
    #         v26-luna / v11-luna / v5-se-*-luna  → audio/mp4  (播放器认作音频, 有声)
    #         v5-ex-luna / v5-luna                → video/mp4  (播放器当视频起链, 无声)
    #      同一份字节, 只有响应头不同(已 md5 逐字节核对: 头 256KB + 尾 8KB 完全一致)。
    #   2) 同一 URL 的 Content-Type 是**粘滞**的(同客户端连续 8 次 HEAD 全部一致), 所以
    #      「先探测出 audio/mp4 的地址, 再交给播放器」是可靠的。
    #   3) 换域名无效(签名绑定 host, 换 host 一律 403); 改路径加 .m4a 也 403;
    #      但追加任意 query 参数不影响(CDN 忽略未知参数)。
    #   4) CDN 对请求头完全不挑(任意 UA / 无 Referer 均 200/206 + 正确字节)。
    #   5) 每首曲目有 12 个候选地址(seo 的 main/backup × 各档 + VOD GetPlayInfo 的
    #      main/backup × 各档), 实测至少 6 个是 audio/mp4。
    # 故播放官方档位时, 逐个候选探测, 取第一个「头是 audio/* 且真能取到字节」的地址。
    # 探测分两级(见 `_pick_verified`): 先用便宜的 HEAD 把所有候选筛一遍, 再只对幸存者
    # 做一次带 Range 的真取数 —— 后者是为了剔除「头正常、字节不下来」的死节点。
    def _app_candidates(self, data, quality):
        """seo_track 里该档位的候选地址(main_url / backup_url)"""
        out = []
        player = data.get("track_player") if isinstance(data.get("track_player"), dict) else {}
        model = player.get("video_model")
        if isinstance(model, str) and model:
            try:
                model = json.loads(model)
            except Exception:
                model = {}
        for item in (model or {}).get("video_list") or []:
            if not isinstance(item, dict):
                continue
            meta = item.get("video_meta") or {}
            if str(meta.get("quality") or "") != str(quality):
                continue
            for field in ("main_url", "backup_url"):
                if item.get(field):
                    out.append(str(item[field]))
        return out

    def _app_candidates_vod(self, data, quality):
        """备用端点 url_player_info(字节 VOD GetPlayInfo)里该档位的候选地址"""
        player = data.get("track_player") if isinstance(data.get("track_player"), dict) else {}
        upi = player.get("url_player_info")
        if not upi:
            return []
        box = ((self._req_url(str(upi)).get("Result") or {}).get("Data") or {})
        out = []
        for item in box.get("PlayInfoList") or []:
            if str(item.get("Quality") or "") != str(quality):
                continue
            for field in ("MainPlayUrl", "BackupPlayUrl"):
                if item.get(field):
                    out.append(str(item[field]))
        return out

    #      ↓ 补充(同日实测用户设备反馈): 只按响应头挑地址还不够 —— 出现过「HEAD 看起来是
    #        audio/mp4, 交给播放器却**一直转圈/黑屏**(EXO 与 MPV 都拉不动)」, 说明
    #        backup_url 那一族里存在「头正常、字节不下来」的死节点。故最终判据加一条
    #        **真取数**(见 `_can_pull`); 为不拖慢起播, 先用便宜的 HEAD 筛, 只对幸存者真拉。
    _PROBE_HEAD_TIMEOUT = 2.5      # 单条候选 HEAD 超时(设备弱网下也别超 3s)
    _PROBE_HEAD_MAX = 4            # 单轮最多 HEAD 几条候选
    _PROBE_PULL_MAX = 2            # 单轮最多对几条幸存者做真取数
    _PROBE_PULL_TIMEOUT = 3.5      # 真取数超时

    def _head_is_audio(self, url):
        """便宜探测: HEAD 一下, 只回答「连得上 + Content-Type 是 audio/*」。

        这只是**初筛**, 不能当最终判据(见 `_can_pull` 的说明)。
        """
        if requests is None:
            return False
        try:
            r = requests.head(url, headers=self._play_headers(),
                              timeout=self._PROBE_HEAD_TIMEOUT, allow_redirects=True)
            ctype = str(r.headers.get("Content-Type") or "").lower()
            return r.status_code in (200, 206) and ctype.startswith("audio/")
        except Exception:
            return False

    def _can_pull(self, url):
        """最终判据: 带 Range 真读一小段字节, 确认 CDN **确实会下发数据**。

        ★为什么必须真拉: 用户实测官方档位「一直转圈/黑屏」, EXO 与 MPV 都拉不动 ——
        即连接建立了(HEAD 200 + 头也正常)但字节不下来。只信响应头就会把这种死地址
        交给播放器, 结果是无限转圈。这里拿不到字节一律判不可用 → 调用方回落。
        """
        if requests is None:
            return False
        try:
            g = requests.get(url, headers=dict(self._play_headers(), **{"Range": "bytes=0-2047"}),
                             timeout=self._PROBE_PULL_TIMEOUT, allow_redirects=True, stream=True)
            try:
                if g.status_code not in (200, 206):
                    return False
                for piece in g.iter_content(512):     # 真读一小段, 确认有字节
                    return bool(piece)
                return False
            finally:
                g.close()
        except Exception:
            return False

    def _pick_verified(self, urls):
        """从候选里挑一个「头是 audio/* 且真能取到字节」的地址; 没有则返回 ''。

        开销刻意压到最低: 先对最多 `_PROBE_HEAD_MAX` 条做 HEAD 初筛(快), 再只对其中
        最多 `_PROBE_PULL_MAX` 条做真取数(慢)。正常网络下每条 HEAD ~0.1-0.3s, 整体
        在 1s 内出结果; 网络不通时最坏 ~2.5s×4 就止损, 不会无限转圈。
        """
        heads = []
        for url in _uniq(urls)[:self._PROBE_HEAD_MAX]:
            if self._head_is_audio(url):
                heads.append(url)
        for url in heads[:self._PROBE_PULL_MAX]:
            if self._can_pull(url):
                return url
        return ""

    def _app_audio_url(self, data, track_id, quality):
        """返回该档位一个**本机实测可播**的官方地址; 探测关闭或找不到时返回 ''(调用方回落)。

        ★**默认关闭**(`app_probe` 默认 0) —— 返回 '' 后 `playerContent` 用 `chosen["url"]`
        (seo 自带的 main_url), 即**逐字节等同于原版行为**。为什么默认关:
          1) ★实测(多采样): seo 的 main_url **每次随机落在两个 CDN 节点之一**, 其中一个是
             `audio/mp4`、另一个是 `video/mp4`, 故探测会以约 **50% 概率把原版本要用的地址
             换成另一个节点** —— 也就是说它**不是**无副作用的信息增益, 而是会改变结果;
             用户报「这次不能播放了」时它刚好默认开启, 关闭后官方档位即恢复可播;
          2) 起播要多花 0.6~1.1s;
          3) 用户明确要求「保持官方地址」(不要第三方回落), 保持原版最符合该预期。
        需要对照排查时 extend 传 "app_probe":1 打开。

        打开后的判据两条, 缺一不可: ① Content-Type 是 audio/*; ② 本机真能取到字节。
        ② 是必须的: 实测 backup_url 一族里存在「HEAD 头正常、字节不下来」的死节点。

        注意: 每次 seo_track 拿到的 URL 会被随机指到不同 CDN 节点, 而节点决定 Content-Type,
        所以单次探测可能全落在 video/mp4 上 → 失败时**重取一次 seo_track 再探**(节点会变)。
        """
        if not self._flag("app_probe", False):
            return ""
        key = (str(track_id), str(quality))
        now = time.time()
        hit = _APP_PROBE_CACHE.get(key)
        if hit and now - hit[1] < 300:
            return hit[0]
        picked, cur = "", data
        # 第 1 轮: 当前数据; 第 2 轮: 重取 seo_track(节点会变, 值得再试一次)
        for attempt in range(2):
            # 先只用 seo 候选(main_url / backup_url, 零额外请求);
            # 都不行才去问 VOD GetPlayInfo 端点 —— 那次请求本身也要几百 ms, 不该每次都发。
            picked = self._pick_verified(self._app_candidates(cur, quality))
            if not picked:
                try:
                    vod_urls = self._app_candidates_vod(cur, quality)
                except Exception:
                    vod_urls = []
                picked = self._pick_verified(vod_urls)
            if picked or attempt:
                break
            try:
                fresh = self._seo(track_id)
                if isinstance(fresh, dict) and fresh.get("track_player"):
                    cur = fresh
            except Exception:
                pass
        _APP_PROBE_CACHE[key] = (picked, now)
        return picked

    def _play_headers(self):
        return {"User-Agent": UA, "Referer": "https://music.douyin.com/"}

    @staticmethod
    def _safe(name):
        return str(name or "播放").replace("$", " ").replace("#", " ")

    def _track_detail(self, track_id):
        track_id = str(track_id)
        data = self._seo(track_id)
        track = self._track(data.get("seo_track") or {}) or {"id": track_id}
        card = self._card(track) or {"vod_id": track_id, "vod_name": "汽水音乐", "vod_pic": ""}
        artists = " / ".join(str(a.get("name") or "") for a in (track.get("artists") or [])
                             if isinstance(a, dict) and a.get("name"))
        album = track.get("album") if isinstance(track.get("album"), dict) else {}
        streams = self._streams(data)
        name = self._safe(track.get("name"))
        if streams:
            sources = [s["label"] for s in streams]
            urls = ["%s$a:%s:%s" % (name, track_id, s["key"]) for s in streams]
        else:
            sources, urls = ["汽水音乐"], ["%s$a:%s:auto" % (name, track_id)]
        # ★第三方 MP3 兼容线路已移除(第十轮): 它当年只是为了「官方档位不出声时仍有个能听的源」,
        #   官方档位在 App 侧关掉「音频直通」后已能正常出声 → 该线路失去存在理由。
        #   现只保留「VIP替代」, 它解决的是**另一个**问题: 会员/试听曲官方只放片段(实测 60s)。
        vip = self._is_vip(data, streams)
        clip = self._clip_seconds(streams)
        if vip:
            # 线路 id 直接把「歌名+歌手」编进去 → 播放时无需再回查 seo_track, 少一次请求
            alt_id = self._pack("m", {"n": str(track.get("name") or name), "r": artists, "t": track_id})
            sources = ["VIP替代"] + sources
            urls = ["%s$%s" % (name, alt_id)] + urls
            self._prefetch_alt([alt_id])      # 后台预热直链, 用户点播放即秒开
        lyric = str(((data.get("lyric") or {}).get("content")) or "")
        if vip:
            mark = "（官方仅%d秒·已加替代源）" % int(clip) if clip else "（会员曲·已加替代源）"
        else:
            mark = ""
        vod = dict(card)
        vod.update({
            "type_name": "音乐",
            "vod_actor": artists,
            "vod_remarks": (str(card.get("vod_remarks") or "").split(" · ")[0] + mark),
            "vod_content": "专辑：" + str(album.get("name") or "未知专辑") + ("\n" + lyric[:1500] if lyric else ""),
            "vod_play_from": "$$$".join(sources),
            "vod_play_url": "$$$".join(urls),
        })
        return vod

    def _collection_detail(self, info):
        """合集(歌单/电台/榜单/听歌模式) → 曲目列表。

        ★听歌模式(preference / scene)不再用「热歌榜/新歌榜/怀旧电台」或「按模式名搜索」
          兜底 —— 那些拿到的列表和官方**根本不是一回事**(见文件头「第十一轮」)。
          现直接走官方同款接口:
            偏好模式 → POST /luna/pc/discover/mix  {mode: default|familiar|fresh}
            场景模式 → POST /luna/pc/discover/mix  {scene_mode_id: N}
          再把该模式下的歌单展开成曲目, 默认凑够 `mode_count`(50) 首。
        """
        kind, rid = str(info.get("kind") or ""), str(info.get("id") or "")
        want = self._mode_want()
        if kind == "chart":
            tracks = self._chart_tracks(rid)
        elif kind == "playlist":
            tracks = self._playlist_tracks(rid)
        elif kind == "radio":
            tracks = self._radio_tracks(rid, want)
        elif kind == "preference":
            tracks = self._feed_mode_tracks(mode=rid or "default", want=want)
            if not tracks and rid == "familiar":        # 最后兜底: 怀旧电台
                tracks = self._radio_tracks(NOSTALGIA_RADIO, want)
        elif kind == "scene":
            tracks = self._feed_mode_tracks(scene_id=rid, want=want)
        else:
            tracks = []                                 # 未知 kind(防御): 下面按名字搜索
        if not tracks:
            tracks = self._search_tracks(info.get("name") or "热门歌曲")
        return self._playlist_card(info, tracks)

    def _mode_want(self):
        """听歌模式/电台一次要拿多少首(extend 的 mode_count, 默认 50, 上限 200)。

        TVBox 的详情页**没有分页**(一次返回全部集数), 做不到官方那种「查看更多继续
        加载」, 所以这里直接一次给足; 想更多就把 mode_count 调大。
        """
        try:
            n = int(str((self._cfg or {}).get("mode_count") or 50).strip() or 50)
        except Exception:
            n = 50
        return max(20, min(200, n))

    def _search_tracks(self, keyword, page=1):
        payload = {"search_type": "track", "q": str(keyword),
                   "cursor": None if page == 1 else str((page - 1) * 20),
                   "search_id": str(keyword), "search_method": "input", "search_scene": "search_result"}
        data = self._req("/luna/search/track", payload, {"device_platform": "web"})
        group = next((g for g in (data.get("result_groups") or []) if g.get("id") == "tracks"), {})
        return [t for t in (self._track(x) for x in (group.get("data") or [])) if t]

    def _chart_tracks(self, chart_id):
        data = self._req("/luna/charts/" + str(chart_id))
        chart = data.get("chart") if isinstance(data.get("chart"), dict) else {}
        items = (chart.get("track_ranks") or chart.get("tracks") or data.get("track_ranks") or
                 data.get("tracks") or data.get("items") or [])
        return [t for t in (self._track(x) for x in items) if t]

    def _mode_playlists(self, scene_id="", mode=""):
        """官方 `/luna/pc/discover/mix`: 取官方推荐歌单池(用于补足曲目)。

        返回 `[(playlist_id, count_tracks), ...]`, **保持服务端原始顺序**; 拿不到返回 []。

        ★不要按曲数排序! 服务端是按相关性排的, 按曲数降序会把「经典摇滚入坑指南」这类
          **大而泛**的歌单顶到第一位(实测踩过这个坑)。

        ⚠️ 实测 `scene_mode_id` / `mode` 对未登录请求**基本不过滤**: 同一 scene 连采样
          4 次歌单集合**零交集**, 跨场景交集率(~5~9/33)与「完全不带场景」的基线相同。
          即这个接口返回的是一**个巨大的随机推荐池**; 早先单次采样看到的「动感健身→
          刷脂电音」只是巧合。参数仍照传(服务端认了就自动生效), 但源侧不依赖它做过滤。
        """
        body = {"block_type": "discovery_playlist", "sub_channel_id": 0,
                "exposure_radio_list": [], "cursor": "", "count": 20}
        if scene_id not in (None, ""):
            try:
                body["scene_mode_id"] = int(str(scene_id))
            except Exception:
                body["scene_mode_id"] = str(scene_id)
        if mode:
            body["mode"] = str(mode)
        data = self._req("/luna/pc/discover/mix", body)
        out = []
        for block in (data.get("inner_block") or []):
            for res in (block.get("resources") or []):
                pl = ((res.get("entity") or {}).get("playlist") or {})
                pid = str(pl.get("id") or "")
                if pid:
                    out.append((pid, int(pl.get("count_tracks") or 0)))
        return out                                   # 保持服务端顺序(相关性优先)

    def _feed_mode_tracks(self, scene_id="", mode="", want=50):
        """听歌模式曲目: 用官方推荐歌单(`discover/mix`)展开, 凑够 want 首。

        为什么这么取(全部实测):
          ① `POST /luna/pc/discover/mix` 是官方推荐内容池, 返回 `inner_block[].resources[]`
             `.entity.playlist`; 用 `POST /luna/playlist/detail`(count=300) 展开即曲目。
             实测一个歌单动辄 100+ 首(「经典摇滚入坑指南」121 首) → 通常 1~2 次请求够 50。
          ② **不用** `POST /luna/pc/feed/song-tab`(官方推荐队列)当主路径, 尽管它才是"进模式
             后真正播放的流": 它每次固定 6 首、忽略 count、**且对所有 scene/mode 参数返回的
             都是同一条随机流**(实测 7 个模式的前 3 首几乎完全一样) → 用它会让所有模式
             长得一模一样, 还慢 3 倍(3s vs 1s)。故不采用。
        合计约 1~1.5s, 且有 600s 缓存(推荐池是随机采样, 不缓存会让详情页每次结果都变)。

        ⚠️ 未登录拿不到「场景专属流」(见 `_mode_playlists` 的说明): 同一场景连采样 4 次
          歌单集合零交集, 跨场景交集率与「不带场景」的基线相同。所以各模式拿到的是
          **官方推荐池的不同随机采样** —— 模式之间内容不同(观感上"每个模式一个样"),
          但不是服务端按场景精确过滤的结果。这仍远好于旧实现(旧的是「默认→热歌榜,
          熟悉→怀旧电台, 新鲜→新歌榜」和「场景→按模式名搜索」, 与官方无关)。
          `scene_mode_id` / `mode` 照传, 服务端认了就自动生效。
        """
        key = "s:%s|m:%s|%d" % (scene_id, mode, want)
        now = time.time()
        hit = _MODE_TRACK_CACHE.get(key)
        if hit and now - hit[1] < _MODE_TRACK_TTL:
            return hit[0]
        tracks, seen = [], set()
        for pid, _count in self._mode_playlists(scene_id, mode):
            if len(tracks) >= want:
                break
            try:
                part = self._playlist_tracks(pid)
            except Exception:
                part = []
            for t in part:
                tid = str((t or {}).get("id") or "")
                if tid and tid not in seen:
                    seen.add(tid)
                    tracks.append(t)
        tracks = tracks[:want]
        if tracks:
            _MODE_TRACK_CACHE[key] = (tracks, now)
            if len(_MODE_TRACK_CACHE) > 60:            # 简单清理, 防无界增长
                for k in list(_MODE_TRACK_CACHE)[:20]:
                    _MODE_TRACK_CACHE.pop(k, None)
        return tracks

    def _radio_tracks(self, radio_id, want=50):
        """电台曲目: 官方每次只回 **6 首**, 且 `count` / `limit` / `cursor` / `offset`
        参数**全都不生效**(实测 9 种变体都固定 6 条), 结果还是随机流 → 只能多轮累积去重。
        电台 id **不是 playlist id**(`playlist/detail` 回 `status_code=1000005`),
        也没有别的电台详情端点(试过 `/luna/radio/detail`、`/luna/pc/radios/{id}` 全 404)。

        ★这是「获取的播放列表数据太少」的第二个来源(第一个是听歌模式走错了数据源)。
          轮数硬上限 6 轮(每轮 ~0.6s, 合计 ~3.5s): 随机流再多拉收益递减(实测 12 轮
          → 去重 24 首), 所以不追求凑满 want, 够不到就返回现有的。
        """
        tracks, seen = [], set()
        rounds = max(3, min(6, (max(1, want) // 12) + 3))
        for _ in range(rounds):
            data = self._req("/luna/feed/radio/tracks", {
                "radio_id": str(radio_id), "played_media": [],
                "feed_radio_media_extra": {"real_groups": []}, "flow_type": 2, "full_media": True})
            items = data.get("items") or []
            if not items:
                break
            for x in items:
                t = self._track(x)
                tid = str((t or {}).get("id") or "")
                if t and tid and tid not in seen:
                    seen.add(tid)
                    tracks.append(t)
            if len(tracks) >= want:
                break
        return tracks[:want]

    def _playlist_tracks(self, playlist_id):
        data = self._req("/luna/playlist/detail", {
            "playlist_id": str(playlist_id), "cursor": None, "count": 300, "type": None,
            "feed_playlist_extra": {"har": None, "commerce_block_pattern": None},
            "sort_type": None, "session_id": None, "reverse": False, "ab_param": "",
            "limited_free_scene": 0}, {"max_length": 4194304})
        return [t for t in (self._track(x) for x in (data.get("media_resources") or [])) if t]

    def _playlist_card(self, info, tracks):
        """合集 → 一条多线路 vod(每档音质一条线路, 每首一个分集)"""
        valid = [t for t in tracks if t and t.get("id")]
        # ★取「档位最全」的那首来定线路(而非第一个有结果的): 实测某些曲目只放 1 档,
        #   若碰上它, 整张合集就只剩 1 条线路(用户会觉得"线路/数据太少")。
        #   最多仍只探 3 首, 拿到 3 档即提前结束 —— 与旧逻辑同样的请求成本。
        streams, best = [], 0
        for t in valid[:3]:
            try:
                cur = self._streams(self._seo(t["id"]))
            except Exception:
                cur = []
            if len(cur) > best:
                streams, best = cur, len(cur)
            if best >= 3:
                break
        name = str(info.get("name") or "汽水音乐")
        if streams:
            sources = [s["label"] for s in streams]
            groups = ["#".join("%s$a:%s:%s" % (self._safe(t.get("name")), t["id"], s["key"])
                               for t in valid) for s in streams]
        else:
            sources = ["最高音质"]
            groups = ["#".join("%s$a:%s:auto" % (self._safe(t.get("name")), t["id"]) for t in valid)]
        # ★不再补第三方 MP3 线路(第十轮已移除, 详见 _track_detail 与文件头注释)
        return {
            "vod_id": self._pack("c", info),
            "vod_name": name,
            "vod_pic": info.get("pic") or "",
            "vod_remarks": info.get("desc") or "",
            "vod_content": info.get("desc") or name,
            "vod_play_from": "$$$".join(sources),
            "vod_play_url": "$$$".join(groups),
        }

    def _video_detail(self, video):
        dur = int(video.get("dur") or 0)
        return {
            "vod_id": self._pack("v", video),
            "vod_name": video.get("name") or "听抖音",
            "vod_pic": video.get("pic") or "",
            "vod_remarks": "%d:%02d" % (dur // 60, dur % 60) if dur else "听抖音",
            "vod_content": video.get("name") or "",
            "vod_play_from": "听抖音",
            "vod_play_url": "播放$v:" + str(video.get("vid")),
        }

    # ------------------------------------------------------------------ 播放
    def _flag(self, key, default=True):
        """读 extend 配置里的开关; 缺省按 default。"""
        raw = (self._cfg or {}).get(key, None)
        if isinstance(raw, list):
            raw = raw[0] if raw else None
        if raw is None or raw == "":
            return default
        return str(raw).strip().lower() not in ("0", "false", "off", "no")

    def _play(self, url, ext=None):
        """组装播放结果(★默认与原版「蜜果版」完全一致, 这是实测确认有声音的形态)。

        - 直连上游, **默认不走本地代理**: 实测「原版有声音 / 加代理后无声」——播放器
          不接受 127.0.0.1 地址(不少 TVBox 系播放器对 loopback 有限制), 一旦包成
          http://127.0.0.1:10010/audio/... 就整条线路无声。代理仅为实验性功能,
          extend 传 "proxy":1 才启用。
        - **默认带 music_player: 1**: 原版一直输出该标记且能正常出声, 它是手机端
          「音乐播放器分流」标记; 去掉它反而会让部分播放器走视频分支。传 "music_player":0 可关。
        - ★**`format` 默认不回填**(`audio_format` 默认 0): `format` 含 "audio" 会命中
          App 的 `AudioUtil.isAudio()` 判据①, 把这条流**分流到 AudioActivity**(专用音频
          播放器); 但仅在**非沉浸式**下有效, 沉浸式(默认)下 `startIfAudio` 直接 false。
          既然原版没这个字段, 就保持不填。传 "audio_format":1 才回填(仅供对照排查)。
        """
        url = str(url or "")
        if url and self._flag("proxy", False):
            url = _proxy_url(url, ext) or url
        out = {"parse": 0, "jx": 0, "url": url, "header": self._play_headers()}
        if self._flag("music_player", True):
            out["music_player"] = 1
        if self._flag("audio_format", False):
            out["format"] = _CTYPE.get(ext or _ext_of(url, ".m4a"), "audio/mp4")
        return out

    def _third_party_play(self, name, artist, track_id):
        """「VIP替代」线路: 拿第三方完整音源(酷我直连优先); 失败回落官方最高档。

        ★仍保留第三方取流的原因: 会员/试听曲官方只放 ~60s 片段, 这条线路要给完整版。
        与已移除的「MP3 兼容线路」不同 —— 那条是为了「官方不出声」兜底, 现在官方能出声了。
        """
        name = str(name or "").strip()
        if name:
            url, ext = self._alt_url(name, artist)
            if url:
                return self._play(url, ext)
        track_id = str(track_id or "")
        if track_id:                                   # 替代源不可用 → 回落官方档, 不阻断播放
            data = self._seo(track_id)
            streams = self._streams(data)
            if streams:
                url = self._app_audio_url(data, track_id, streams[0]["key"]) or streams[0]["url"]
                return self._play(url)
        return None

    def playerContent(self, flag, id, vipFlags=None):
        value = str(id or "")
        try:
            if value.startswith("v:"):
                url = ("https://aweme.snssdk.com/aweme/v1/play/?"
                       "video_id=%s&ratio=1080p&line=0" % value[2:])
                return {"parse": 0, "jx": 0, "url": url, "header": {"User-Agent": UA}}
            # 新形态: 「歌名+歌手+track_id」已编进 id → 免掉一次 seo_track 回查, 起播更快
            if value.startswith("m:"):
                info = self._unpack(value, "m") or {}
                out = self._third_party_play(info.get("n"), info.get("r"), info.get("t"))
                if out:
                    return out
                return {"parse": 1, "jx": 0, "url": value, "header": {}}
            if value.startswith("a:"):
                _, track_id, quality = value.split(":", 2)
            else:
                track_id, quality = value, "auto"
            data = self._seo(track_id)
            if quality in ("vip", "mp3"):
                # "vip" = 当前「VIP替代」线路; "mp3" 仅为**历史缓存列表**的旧 id 兼容
                # (新生成列表已不再产生 mp3 线路, 见文件头「第十轮」)。
                track = self._track(data.get("seo_track") or {}) or {}
                out = self._third_party_play(track.get("name"), self._artists(track), track_id)
                if out:
                    return out
                quality = "auto"  # 第三方不可用 → 回落官方档位, 不阻断播放
            streams = self._streams(data)
            chosen = next((s for s in streams if s["key"] == quality), streams[0] if streams else None)
            if not chosen:
                return {"parse": 1, "jx": 0, "url": value, "header": {}}
            # 官方档位默认直连 chosen["url"](= seo 的 main_url, 与原生行为逐字节一致)。
            # extend 传 "app_probe":1 时才会去挑 CDN Content-Type=audio/mp4 的候选地址
            # (★默认关闭: 探测会以约 50% 概率把地址换到另一个 CDN 节点, 反而更不稳)。
            url = self._app_audio_url(data, track_id, chosen["key"]) or chosen["url"]
            return self._play(url)
        except Exception:
            return {"parse": 1, "jx": 0, "url": value, "header": {}}

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def localProxy(self, params):
        return [404, "text/plain", b""]


if __name__ == "__main__":
    print(json.dumps(Spider().homeContent(True), ensure_ascii=False, indent=2))
