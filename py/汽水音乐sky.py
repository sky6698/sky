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
#     - ~~主数据源: `POST /luna/pc/discover/mix` 的官方推荐歌单池, 用 `playlist/detail`
#       展开~~ → **第十二轮已弃用**: 那个池子是按**流派**拼的(摇滚/电音/J-pop/indie/
#       欧美民谣…), 抽到什么看运气, 加上 `scene_mode_id` 零过滤 → 结果「模式里全是
#       英文歌」。详见下面第十二轮。
#     - `POST /luna/pc/feed/song-tab`(官方推荐队列, `items[].entity.track_wrapper.track`)
#       每次固定 6 首、忽略 count、对所有 `scene_mode_id`/`mode` 返回同一条随机流, 但
#       **81% 是中文** → 第十二轮改为**兜底**用它补充(不再当主路径)。
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
#   改动(第十一轮): 1) 新增 `_feed_mode_tracks()`;
#         2) `kind="preference"` / `"scene"` 改走它, **删掉**「热歌榜/新歌榜/怀旧电台顶替」
#            与「按模式名搜索」两条兜底(怀旧电台仅留作 familiar 的最终兜底);
#         3) `_radio_tracks(radio_id, want)` 增加多轮累积去重;
#         4) 新增 `mode_count` 开关与 `_mode_want()`; 新增 `_MODE_TRACK_CACHE`(600s 缓存,
#            推荐流是随机采样, 不缓存会让详情页每次结果都变)。
#
# ★★★ 第十二轮(2026-10-13): **听歌模式改为中文优先(修「模式都变成英文歌了」)**
#   用户反馈: 「模式都变成英文歌了, 官方 app 里都是好听的中文歌」。
#   根因: 第十一轮的主数据源 `discover/mix` 歌单池**是按流派拼的**(摇滚/电音/J-pop/
#         indie/欧美民谣…), 抽到什么全看运气; 且 `scene_mode_id` 对未登录请求零过滤
#         → 于是满屏外文歌。
#   新数据源(全部实测):
#     ① **主题搜索** `POST /luna/search/track`, 关键词取 MODE_KEYWORDS(按模式名归一)。
#        命中准且是中文 —— 粤语→灰色轨迹/傻女/富士山下, 国风→醉春烟/破阵曲,
#        助眠→助眠轻音乐, 车载→中文经典老歌。
#     ② **官方中文榜单**: 热歌榜(**94% 中文**, 50 首 / 0.23s) + 新歌榜(86% 中文)。
#        「好听的中文歌」主要来自这里, 也保证一次给足 `mode_count` 条。
#     ③ **官方推荐流** `song-tab`(81% 中文) 降级为**兜底**(①②通常已够 50, 走不到)。
#   ⚠️ **不做全局中文过滤**: 「欧美 / 日语 / k-pop」三个**语种/地区模式**本来就该是外文歌
#      → 它们改用①的关键词多翻 2 页, **不掺中文榜单**(实测 k-pop 模式 0% 中文, 正确)。
#   实测: 默认/熟悉/新鲜/图书馆/动感健身/粤语/深夜EMO/洗澡/驾车 均 **96% 中文**、50 首、
#         0.7~1.9s; 欧美(外文)/日语/ k-pop 保持原语种。
#   改动: 1) 新增 `MODE_KEYWORDS`(48 个模式 → 中文主题词) + `MODE_FOREIGN` + `_mode_key()`;
#         2) `_feed_mode_tracks(scene_id, mode, name, want)` 重写为「主题搜索 → 中文榜单 →
#            推荐流」三级, 并接收模式名以便查关键词; `_mode_playlists()` **删除**(英文源头);
#         3) `_collection_detail()` 把 `info["name"]` 透传给 `_feed_mode_tracks()`。
#
# ★★★ 第十三轮(2026-10-13): **加「登录」分类(扫码登录 / 手动拉起官方 App 授权)**
#   用户需求: 「分类最后加登录, 分扫码登录 / 手动拉起官方 app 授权登录; 没登录按现在模式,
#              登录后按官方 app 模式获取」。
#   ★官方登录链路(纯 HTTP 实测可用, **不需要签名页 / Chromium**):
#     - 创建二维码  GET  `https://api.qishui.com/passport/web/get_qrcode/?<公共参数>`
#         · 公共参数**全部放 query**(不是 body); **aid=386088** 是关键
#           (填 2329 / 6383 会回 `error_code=22 非法应用`)。
#         · 必须带 `x-tt-passport-verify-portrait: <uuid>.login` 与
#           `x-tt-passport-trace-id: <8位hex>`; UA 用汽水 PC 客户端
#           (Electron/SodaMusic, 见 `QR_UA`)。
#         · 回包 `data.qrcode` = `data:image/png;base64,...` —— **官方直接给渲染好的
#           二维码图(约 18KB)**, 所以源里**不必内置二维码编码器**;
#           `data.qrcode_index_url` = `https://bff-pc.qishui.com/ucenter_web/app/sdk-next?…&uc_sdk=scan-auth`
#           = **二维码内容(官方原样)**; 另有 `data.token` / `data.expire_time`。
#     - 轮询状态    POST `/passport/web/check_qrconnect/?<公共参数>`
#         · body 用 form-urlencoded(token / need_logo / need_short_url / is_frontier /
#           is_new_login / next), 并带 `x-ss-stub = MD5(body).upper()`。
#         · `data.status`: `new` → `scanned` → `confirmed`; `error_code=7` 是**临时限流**
#           (应继续轮询, 不能判失败); 只有 `error_code=2` / `status=expired` 才是过期。
#     - 登录态: `confirmed` 时 Cookie 随 Set-Cookie 下发(会话里出现 `sessionid` /
#       `sessionid_ss` / `sid_guard` / `sid_tt` 即成功)。拿到后**落盘持久化**,
#       之后内容类请求都带上它 —— 服务端这时才认 `scene_mode_id` / `mode`
#       (匿名请求对这两个参数**零过滤**, 见第十一/十二轮)。
#   ⚠️ 二维码内容**必须用官方 `qrcode_index_url` 原样**: 上游另一份参考实现
#      (Laine127/libresoda 的 tools/qishui-qr.py)把二维码改写成
#      `bff-pc.qishui.com/light/invoke/scan_login?token=…`, 其 docs/QR-LOGIN.md 明确记录
#      该形态「只上报 scanned, 确认后永远停在 scanned」→ **不能用**。
#   ⚠️ 风险(如实记录): 官方对**裸 HTTP 请求**有风控, 可能一路回 `error_code=7 访问太频繁`
#      → 扫码后拿不到 `confirmed`。此时用第三条通路兜底: 搜索框输入
#      `#登录 <Cookie>` 手动粘贴(见下 "手动 Cookie 通道")。
#   ★实现形态(TVBox 没有交互界面, 用「分类卡片 + 本地小服务」模拟):
#     - 「登录」分类排在最末, 未登录时给两张卡:
#         「扫码登录」   ← 卡片封面(vod_pic)就是**官方的二维码 PNG**(本机 /qr 转发)
#         「App 授权登录」← 手机浏览器打开本机 `/login` 页(页内二维码 + 「打开汽水音乐
#                          App 完成授权」按钮), 即「手动拉起官方 App 授权」
#         点开任一张 → 详情页会**轮询一次**并把结果写进简介: 手机扫码确认后**再点一次**
#         (或返回再进)即可看到「✅ 登录成功」→ 登录态落盘。
#     - 已登录时给两张卡: 「已登录：<昵称>」(点开看账号) + 「退出登录」。
#     - 登录服务监听 `0.0.0.0`(手机要能打开 `/login`), 端口 10020 起顺序探测;
#       **音频代理仍只监听 127.0.0.1**(不外泄)。
#   ★登录后取数变化: `_feed_mode_tracks()` 优先走 `_feed_official()` ——
#     `POST /luna/pc/discover/mix`(带 scene_mode_id / mode) → 官方歌单 → `playlist/detail`
#     展开, 不足再吃个性化 `song-tab` 推荐队列; 失败自动回落到匿名的「主题搜索 + 中文榜单」
#     策略(所以**没登录 = 现在模式, 登录 = 官方 App 模式**, 正是用户要的语义)。
#   ★开关: `"login":0` 关闭登录分类(整块隐藏, 回到纯匿名);
#          `"login_server":0` 不起本地登录服务(此时卡片封面退化为默认图标)。
#
# ================================================================== 宿主弹窗(第十五轮)
# 需求原文: 「点击扫码登录 → 弹出二维码窗口; 点击 App 授权登录 → 直接打开系统上的
#            汽水音乐 App 授权登录」。
# 变动: 登录两张卡片从「点开→详情页写文案+手动刷新」升级为**点一下直接弹内嵌窗口**。
#   ① 「扫码登录」→ 宿主弹 WebView 窗口, 里面是官方二维码 PNG + 实时状态(AJAX, 不闪屏);
#   ② 「App 授权登录」→ 宿主弹 WebView 窗口, 直接打开官方授权深链
#      `data.qrcode_index_url`(`https://bff-pc.qishui.com/ucenter_web/app/sdk-next?…&uc_sdk=scan-auth`)
#      —— 手机浏览器/微信打开这条会**直接唤起手机上的汽水音乐 App**;
#      ⚠️ 但**在本机内嵌 WebView 里点「打开 App」会被宿主拦**(CatWebActivity
#         只放行 http/https, 见下方常量区详注) —— 宿主硬限制, 源侧无解。
#   实现手段: py 源直接调宿主的本地 HTTP 接口 `/msg`(CatMessage, **无来源校验**);
#   宿主不可用时(非 webhtv / 服务未起)**逐字回落到原来的详情页文案链路**。
# 详见常量区 `APP_PORT_RANGE` 上方的事实清单(含 App 源码行号)。
#
# ================================================================== 登录状态同步(第十六轮)
# 需求原文: 「手机确认登录后 这边状态不会更新; 如果登陆成功 这边更新状态;
#            可以去 E:\DCBrowserDownloads\webhtv-5.6.0-202609192305 看看是怎么确认状态、
#            存储登录信息」。
#
# ①「状态不会更新」的真实原因(**不是 UI bug, 是这条路本来就拿不到登录态**):
#   上游 libresoda `docs/QR-LOGIN.md` 的真机实测(2026-09-15)逐条对上:
#     · 状态机 = `new → scanned → confirmed`; `error_code=7` 是**临时限流**, 冷却必须 5s
#       (「写成 60 秒会把整个扫码→确认窗口跳过去, 表现为卡在 scanned」);
#     · **纯 HTTP 直连(不带 a_bogus 签名)扫码后会一路 error_code=7, 连 scanned 都读不到**;
#     · **确认后的登录态不在响应体里**(`session_cookie=false`、无 Set-Cookie),
#       「只在签名页浏览器会话里」。
#   本机复现到的响应形态与之吻合: `{"data":{"status":"new","error_code":0,...}}` ——
#   `status` 是**单词**不是数字, 且这一跳只下发 `passport_csrf_token`, 没有 sessionid。
#   ⇒ 所以「手机确认了、这边永远不动」在旧实现下是**必然**的:
#     三个缺陷叠在一起 —— (a) 状态词表不全, 不认识的状态静默回落成「等待扫码」;
#     (b) `error_code=7` 被当成「等待中」, 用户扫码后看不到任何变化;
#     (c) 轮询只挂在登录页的 AJAX 上, **页面一关就断**; 非弹窗链路还会被宿主缓存
#         (`SiteApi.cacheDetail` 缓存详情 5 分钟, 只有「本次 detail 期间开过网页」
#          才跳过缓存, 见 `CatWebEvent.requestedAfter`)。
#
# ②「登录成功后这边更新状态」怎么落地 —— **去宿主的 WebView 里取, 这是唯一有官方浏览器
#   会话的地方**(App 源码事实):
#     · 这个 fork 用 **Chaquopy** 把 Python 3.10 跑在 App 进程内(`chaquo/build.gradle`),
#       源与宿主**同进程同 uid** ⇒ 源能直接读宿主 WebView 的 Cookie;
#     · 读法① 首选 `android.webkit.CookieManager.getInstance().getCookie(url)`
#       (App 自己就这么干: `web/CookieBridge.java:13`, 且被 `WebHomeRawAdapter` /
#        `WebHomeInlineVodStore` 在**后台线程**调用 → 后台线程读是安全的);
#     · 读法② 退路: 直读 `app_webview/**/Cookies` 这个 SQLite
#       (`LoginStateSync.java:802-807` 把它标成 HIGH 置信的登录态载体);
#     · 官方会话从哪来: 用户在**宿主弹出的窗口里**走官方页面(官方 JS, 无直连风控)完成
#       登录/授权 → 会话 Cookie 落在 WebView 的共享 Cookie 库里。
#   ⇒ 实现: 新增**后台守护线程**持续「轮询状态 + 收割宿主 Cookie」, 一旦收割到会话字段就
#     用 `/luna/me` 校验 → 落盘 → 登录分类立刻变「已登录」。状态**不再依赖页面是否开着**。
#
# ③ 顺带修掉的坑(都有出处):
#     · 直连 `redirect_url` 时**手工解析原始 Set-Cookie**: requests 的 cookiejar 会按域名
#       策略**拒收** `Domain=.qishui.com` 这类跨域 Set-Cookie —— 那正是「拿到了 confirmed
#       却永远收不到 sessionid」的另一半原因;
#     · 官方二维码只有 ~90s(`expire_time`), 后台线程**自动换新码**, 不再让用户对着过期码;
#     · `error_code=2046` = 官方要求二次安全验证(需要签名页桥接, 纯 HTTP 做不了)→ 明确提示
#       改用「网页登录」或 `#登录 <Cookie>`, 不再假装还在等扫码。
#
# 开关(写在源配置的 extend 里, 均为可选):
#   "login":0         隐藏「登录」分类(默认 1 = 显示)
#   "login_server":0  不起本地二维码/登录页服务(默认 1)
#   "app_window":0    不调宿主弹内嵌窗口(默认 1); 关掉后登录卡片退回详情页文案模式
#   "login_watch":0   不启后台登录守护线程(默认 1)。★默认必开: 它是「手机确认后这边自动
#                     更新状态 / 自动收割宿主 WebView 会话」的唯一执行者; 关掉后轮询退回
#                     「只在登录页 AJAX 里打」(页面一关就断, 是第十六轮修的旧行为)。
#   "login_host":0    不读宿主 WebView 的 Cookie(默认 1)。仅在你想完全隔离宿主时关。
#   "login_toast":0   登录成功后不弹「✅ 登录成功」窗口(默认 1 = 弹)。
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
import os
import random
import re
import socket
import tempfile
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

# ------------------------------------------------------- 听歌模式 → 官方搜索关键词
# ★为什么需要这张表: 官方「听歌模式」的场景流要**登录态**才拿得到 —— 未登录时
#   `scene_mode_id` / `mode` 参数实测**零过滤**(同一场景连采样 4 次歌单集合零交集,
#   跨场景交集率与「完全不带场景」的基线相同), 而不带主题的通用推荐池是按**流派**
#   拼的(摇滚/电音/J-pop/indie/欧美民谣…), 抽到什么都看运气 → 用户反馈
#   「模式都变成英文歌了, 官方 app 里都是好听的中文歌」。
#   故改为: 按该模式的**中文主题词**走官方**搜索接口**取内容(实测命中率高、基本全中文),
#   再用官方**中文榜单**(热歌榜 94% 中文 / 新歌榜 86% 中文)补足到 mode_count。
# ⚠️ 只有 MODE_FOREIGN 里这三个**语种/地区模式**允许外文内容(欧美/日语/k-pop 本来
#   就该是外文歌); 其余 45 个模式一律**中文优先**, 不掺外文。
MODE_KEYWORDS = {
    "默认模式": "抖音热歌", "熟悉模式": "经典老歌 中文", "新鲜模式": "新歌 中文",
    "深夜emo": "伤感 中文 情歌", "助眠模式": "助眠 轻音乐 舒缓", "洗澡": "民谣 中文 轻松",
    "dj模式": "中文 DJ 舞曲", "动感健身": "运动 燃脂 中文", "抖音漫游": "抖音热歌",
    "chill放松": "chill 中文 放松", "快乐时光": "欢快 中文 流行", "电音": "中文 电音",
    "好运": "好运 中文 喜庆", "图书馆": "轻音乐 钢琴 纯音乐", "粤语": "粤语",
    "通勤必听": "通勤 中文 流行", "失恋必听": "失恋 中文 伤感", "躺平": "慵懒 中文",
    "欧美": "欧美 流行", "打扫": "轻快 中文", "国风": "国风 古风",
    "打游戏": "游戏 战歌 中文", "驾车": "车载 中文 经典老歌", "专注模式": "轻音乐 纯音乐 学习",
    "说唱": "中文说唱", "沉浸0.8x": "抒情 慢歌 中文", "夜晚": "夜晚 中文 抒情",
    "治愈": "治愈 中文", "轻音乐": "轻音乐 纯音乐", "小酒馆": "民谣 小酒馆",
    "ktv必点": "KTV 必点 中文", "起床": "清晨 中文 轻快", "浪漫情歌": "浪漫 中文 情歌",
    "摇滚": "中国摇滚", "r&b": "中文 R&B", "佛系时间": "佛系 安静 中文",
    "怀旧老歌": "怀旧 经典老歌", "民谣": "中文民谣", "甜美女声": "甜美女声 中文",
    "k-pop": "k-pop", "日语": "日语", "旅行": "旅行 中文 轻快",
    "摸鱼": "轻松 中文 摸鱼", "儿歌": "儿歌", "雨天": "雨天 中文 抒情",
    "海边": "海边 中文", "乡村": "乡村 中文", "古典": "古典 钢琴",
}
# 只有这三个模式下允许内容以外文为主(它们本身就是语种/地区模式)
MODE_FOREIGN = ("欧美", "日语", "k-pop")
MODE_FOREIGN_KEYS = {re.sub(r"\s+", "", x).lower() for x in MODE_FOREIGN}
# 主题搜索里常混进「串烧/合集/DJ版」这类**多曲连播的长音频** —— 它们不是"一首歌", 播起来
# 是一个小时的长条。这里**只降序不删除**(有些模式本来就该是合集), 让真歌排在前面。
MODE_JUNK = ("串烧", "连播", "合集", "合辑", "精选集", "伴奏", "铃声", "DJ版", "串烧版")


def _mode_key(name):
    """模式名归一: 去空白 + 转小写。

    接口返回名有 '深夜 EMO' / 'K-pop' / 'Chill 放松' / 'DJ模式' 等大小写与空格不一致的
    写法, 归一后才能与 MODE_KEYWORDS 对上。
    """
    return re.sub(r"\s+", "", str(name or "")).lower()


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
# ================================================================== 扫码登录(第十三轮)
# 需求: 「分类最后加登录, 分扫码登录 / 手动拉起官方 App 授权登录; 没登录按现在模式,
#        登录后按官方 App 模式获取」。完整链路与坑见文件头「第十三轮」。
QR_AID = "386088"                       # ★汽水 PC 客户端的 passport aid(填错回「非法应用」)
QR_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
         "(KHTML, like Gecko) SodaMusic/3.2.1 Chrome/136.0.7103.59 "
         "Electron/36.4.0 Safari/537.36")
QR_GET = "/passport/web/get_qrcode/"
QR_CHECK = "/passport/web/check_qrconnect/"
QR_ME = "/luna/me"                      # 登录态探测: 匿名/失效回 status_code=1000016
QR_SESSION_KEYS = ("sessionid", "sessionid_ss", "sid_guard", "sid_tt")
QR_PORT_RANGE = (10020, 10060)          # 登录服务端口(0.0.0.0, 给手机开 /login)
QR_TTL = 170                            # 二维码兜底有效期(秒); 官方会给 expire_time
_LOGIN_ENABLED = True                   # 由 `init()` 依 extend 的 "login"/"login_server" 改写
_LOGIN_WATCH_ON = True                  # 后台登录守护线程(第十六轮; "login_watch":0 关)
_LOGIN_HOST_ON = True                   # 读宿主 WebView 的 Cookie(第十六轮; "login_host":0 关)
_LOGIN_TOAST = True                     # 登录成功后弹「✅ 登录成功」窗口("login_toast":0 关)
_QR_LOCK = threading.RLock()
_QR_STATE = {"session": None, "png": b"", "token": "", "expire": 0.0, "status": "",
             "scan_url": "", "qrcode_url": "", "desc": "", "born": 0.0, "cookies": "",
             "port": 0, "server": None,
             # 第十六轮: 状态诊断字段(给 UI/回归脚本用, 让「状态变化」看得见)
             "raw": "", "error_code": 0, "cool": 0.0, "limited": False, "verify": False,
             "src": "", "done_pop": False}
_LOGIN_LOCK = threading.RLock()
_LOGIN_STATE = {"loaded": False, "cookie": "", "nick": "", "uid": "", "saved": 0.0}

# ------------------------------------------------- 登录状态机 + 宿主会话收割(第十六轮)
# 完整根因与出处见文件头「第十六轮」。这里只放常量与共享状态。
_QR_POLL = 3.0                      # 后台轮询间隔(秒)
_QR_COOL = 5.0                      # ★error_code=7 的冷却, 必须 5s(上游真机实测结论;
                                    #   写成几十秒会把「扫码→确认」窗口跳过去 → 卡在 scanned)
_QR_WATCH_MAX = 90                  # 后台线程最多跑多少轮就停(没人扫码时不必无限换码)
_QR_STATUS_WORDS = {"new": "new", "0": "new", "1": "new",
                    "scanned": "scanned", "scanning": "scanned", "2": "scanned",
                    "confirmed": "confirmed", "success": "confirmed", "3": "confirmed",
                    "expired": "expired", "expire": "expired", "timeout": "expired",
                    "cancel": "expired", "canceled": "expired"}
_QR_WATCH = {"thread": None}
_HOST_LOCK = threading.RLock()
_HOST_STATE = {"cookie": "", "checked": 0.0, "reject": ""}
HOST_COOKIE_TTL = 2.0               # 宿主 Cookie 的短缓存(秒): 解析列很便宜, 但不能太频繁
HOST_COOKIE_URLS = (                # CookieManager 按 URL 取 → 自带域名过滤, 多打几个域名
    "https://api.qishui.com/", "https://www.qishui.com/", "https://bff-pc.qishui.com/",
    "https://music.douyin.com/", "https://www.douyin.com/")
HOST_LOGIN_URL = "https://www.qishui.com/"   # 汽水官方 Web 版(实测 title「汽水音乐 - 抖音音乐版」)

# ---------------------------------------------------------------- 宿主弹窗(第十五轮)
# ★需求: 「点击扫码登录 → 弹出二维码窗口; 点击 App 授权登录 → 直接打开系统上的汽水
#          音乐 App 授权登录」。
#
# ★事实清单(全部读自**实测 App 源码** mo-webhtv-5.6.0, 不是反编译猜的):
#   · app/.../server/Server.java:66-80
#       宿主 HTTP 服务端口**从 9978 起顺序试**(失败才 +1), 上限 < 9999;
#       `Server.getAddress(true)` = `http://127.0.0.1:<port>`。
#   · app/.../server/Nano.java:44-62
#       路由表(按序): /action /cache /debug /drive /local /m3u8 /manage /media /parse
#       /api/playback /proxy **/msg** /remote /spider /webResource, 另特判 /device /tvbus。
#   · app/.../server/process/CatMessage.java:34-53  ★关键
#       `isRequest` 只判 `url.startsWith("/msg")` —— **没有任何来源/IP/白名单校验**,
#       所以**同机的 py 源可以直接 POST 它**:
#           POST /msg  {"action":"openInternalWebview","opt":{"url":"<任意 http(s)>"}}
#        → `CatWebview.open(url)` → 启动内嵌 `CatWebActivity` → **弹出一个 WebView 窗口**,
#          并顺手 post `CatWebEvent` 让详情页立刻退场(所以不会先闪一个空白详情页)。
#       这就是「弹出二维码窗口」的落地方式, 比在详情页堆文案强一个量级。
#   · app/.../ui/web/CatWebActivity.java:222-228
#       内嵌页 `shouldOverrideUrlLoading` **只放行 http/https**; 非 http(s) 的 scheme
#       (`intent://` / `market://` / 汽水自定义 scheme)**一律丢弃, 明确"不去唤起外部应用"**。
#       ⇒ **宿主主动禁止从内嵌页拉起第三方 App**, 这是设计意图, 不是 bug。
#   · 其余可能的"打开外部 App"通路**全部走不通**(逐条查过, 不再试错):
#       - `/action?do=push|search|setting` → `ServerEvent.*` —— 本 fork **没有任何
#         @Subscribe 订阅者**(全仓库 grep 只有 post 处), 属于死代码;
#       - `/action?do=file&path=` → `FileUtil.openFile` 只对**本地文件** setDataAndType;
#       - `PlayerHelper.choose()` 有 `ACTION_VIEW`, 但入口在播放页菜单里, 源侧触不到;
#       - Lab 的 `open`/`webview`/`qrcode` 动作要用户在 `lab.json` 里预置, 源侧注入不了;
#       - `CatWebview.external()` 的 `ACTION_VIEW` 只在"内嵌页起不来"时兜底, 而
#         `CatWebActivity` 已在 manifest 注册(第 115 行), 正常情况永不触发。
#
# ★结论(如实记录, 避免下次再绕):
#   ① 「扫码登录」= 弹内嵌窗口显示官方二维码 + 实时状态          → **完全可行**;
#   ② 「App 授权登录」= 弹内嵌窗口打开官方授权深链 `qrcode_index_url`
#      (实测形态 `https://bff-pc.qishui.com/ucenter_web/app/sdk-next?…&uc_sdk=scan-auth`)
#      → 是 https, 内嵌页放行, 官方授权页能正常渲染;
#        **手机上**(浏览器/微信)打开这条链接会经 App Links **直接唤起汽水音乐 App 完成授权**;
#        但**本机内嵌 WebView 里点"打开 App"仍会被拦** —— 宿主硬限制, 源侧无解。
#   ⇒ 兜底通道永不删: 搜索框 `#登录 <Cookie>`(见 `_login_command`)与此前的详情页文案链路。
APP_PORT_RANGE = (9978, 9999)           # 宿主 HTTP 服务端口区间(Server.start 从 9978 起)
APP_PORT_TTL = 300.0                    # 命中后的缓存时长(秒)
APP_PORT_MISS_TTL = 20.0                # 未命中的短缓存: 别每点一次卡片就扫一遍端口
APP_DEVICE = "/device"                  # 探测判别用: Nano 特判, 回 Device 的 JSON
APP_MSG = "/msg"                        # CatMessage: 无来源校验 → 本机源可直接 POST
_APP_LOCK = threading.RLock()
_APP_STATE = {"port": 0, "checked": 0.0}
_APP_WINDOW = True                      # 由 `init()` 依 extend 的 "app_window" 改写


def _login_path():
    """登录态落盘位置: 优先 py 源同目录, 不可写则退到临时目录。"""
    cands = []
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        if here:
            cands.append(os.path.join(here, "qishui_login.json"))
    except Exception:
        pass
    try:
        cands.append(os.path.join(tempfile.gettempdir(), "qishui_login.json"))
    except Exception:
        pass
    for path in cands:
        try:
            folder = os.path.dirname(path)
            if folder and os.path.isdir(folder) and os.access(folder, os.W_OK):
                return path
        except Exception:
            continue
    return cands[0] if cands else "qishui_login.json"


def _login_load():
    """懒加载登录态(源可能被反复实例化, 只有落盘才能跨会话保持)。"""
    with _LOGIN_LOCK:
        if _LOGIN_STATE["loaded"]:
            return _LOGIN_STATE
        _LOGIN_STATE["loaded"] = True
        try:
            with open(_login_path(), "r", encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict):
                _LOGIN_STATE["cookie"] = str(data.get("cookie") or "")
                _LOGIN_STATE["nick"] = str(data.get("nick") or "")
                _LOGIN_STATE["uid"] = str(data.get("uid") or "")
                _LOGIN_STATE["saved"] = float(data.get("saved") or 0)
        except Exception:
            pass
        return _LOGIN_STATE


def _login_save(cookie="", nick="", uid=""):
    with _LOGIN_LOCK:
        _LOGIN_STATE["loaded"] = True
        if cookie:
            _LOGIN_STATE["cookie"] = str(cookie)
        if nick:
            _LOGIN_STATE["nick"] = str(nick)
        if uid:
            _LOGIN_STATE["uid"] = str(uid)
        _LOGIN_STATE["saved"] = time.time()
        try:
            with open(_login_path(), "w", encoding="utf-8") as fp:
                json.dump({"cookie": _LOGIN_STATE["cookie"], "nick": _LOGIN_STATE["nick"],
                           "uid": _LOGIN_STATE["uid"], "saved": _LOGIN_STATE["saved"]},
                          fp, ensure_ascii=False)
        except Exception:
            pass
        return _LOGIN_STATE


def _login_forget():
    with _LOGIN_LOCK:
        _LOGIN_STATE.update({"loaded": True, "cookie": "", "nick": "", "uid": "", "saved": 0.0})
        try:
            os.remove(_login_path())
        except Exception:
            pass
        return _LOGIN_STATE


def _login_cookie():
    """当前登录 Cookie(空串 = 匿名 → 走「现在模式」)。"""
    return str((_login_load() or {}).get("cookie") or "")


def _qr_cookie_ok(cookie_text):
    """Cookie 里出现会话字段才算登录成功(只认官方下发的那些 key)。"""
    text = str(cookie_text or "")
    return any(("%s=" % key) in text for key in QR_SESSION_KEYS)


def _cookie_header(jar):
    pairs, seen = [], set()
    try:
        items = list(jar)
    except Exception:
        items = []
    for c in items:
        name, value = getattr(c, "name", None), getattr(c, "value", None)
        if name and value is not None and name not in seen:
            seen.add(name)
            pairs.append("%s=%s" % (name, value))
    return "; ".join(pairs)


def _cookie_pairs(text):
    """`k=v; k=v` → 有序 dict(后出现的同名只补空值, 不覆盖已有值)。"""
    out = {}
    for part in str(text or "").split(";"):
        name, _, val = part.strip().partition("=")
        name, val = name.strip(), val.strip()
        if name and (name not in out or (val and not out[name])):
            out[name] = val
    return out


def _cookie_str(pairs):
    return "; ".join("%s=%s" % (k, v) for k, v in (pairs or {}).items())


def _cookie_merge(old, new):
    """合并两串 Cookie(旧的在前, 新的补上/覆盖非空值)。"""
    pairs = _cookie_pairs(old)
    for key, val in _cookie_pairs(new).items():
        if val or key not in pairs:
            pairs[key] = val
    return _cookie_str(pairs)


def _set_cookie_values(resp):
    """把响应里所有 `Set-Cookie` **手工**拼成 `k=v; k=v`。

    ★为什么不用 requests 的 cookie jar: 官方下发的会话 Cookie 常带
    `Domain=.qishui.com`, 而请求打在 `api.qishui.com` 上时, cookiejar 的默认策略会
    **按域名拒收**这种跨域 Set-Cookie —— 那正是「状态都 confirmed 了, 本地永远收不到
    sessionid」的另一半原因(上游 `docs/QR-LOGIN.md` 也记录「确认后登录态不在响应体」)。
    这里改成自己解析原始响应头, 谁发的都收。
    """
    values = []
    try:
        values = list(resp.raw.headers.getlist("Set-Cookie") or [])
    except Exception:
        try:
            one = resp.headers.get("Set-Cookie")
            values = [one] if one else []
        except Exception:
            values = []
    out = {}
    for item in values:
        pair = str(item or "").split(";", 1)[0].strip()
        name, _, val = pair.partition("=")
        name, val = name.strip(), val.strip()
        if name and (name not in out or val):
            out[name] = val
    return _cookie_str(out)


def _qr_follow(url, sess):
    """跟一跳官方 `redirect_url`, 把会话 Cookie 收上来(手工解析, 见 `_set_cookie_values`)。"""
    http = sess.get("http") if isinstance(sess, dict) else None
    if http is None or requests is None or not url:
        return ""
    try:
        resp = http.get(str(url), allow_redirects=True, timeout=15)
    except Exception:
        return ""
    return _cookie_merge(_set_cookie_values(resp), _cookie_header(http.cookies))


def _qr_norm(status, code=0):
    """官方状态词 → 统一状态。

    ★不认识的状态**原样返回**(而不是静默回落成 "new") —— 旧实现正是靠 `.get(state, "等待扫码…")`
    把陌生状态吞掉, 表现为「手机上都确认了, 这边还写着等待扫码」。现在 UI 会把官方原文显示出来。
    """
    word = str(status or "").strip()
    if word.lower() in _QR_STATUS_WORDS:
        return _QR_STATUS_WORDS[word.lower()]
    if int(code or 0) == 2:
        return "expired"
    return word


def _qr_tip(state, raw="", limited=False, verify=False, code=0):
    """状态 → 页面/详情页上的人话提示。"""
    if limited:
        return "⚠️ 官方临时限流(error_code=7), 已按 5s 冷却自动重试 · 手机上确认即可"
    if verify:
        return "⚠️ 官方要求二次安全验证(error_code=2046) · 请改用「网页登录」或用手机 App 确认"
    table = {"new": "等待扫码…", "scanned": "已扫码, 请在手机上点「确认」",
             "confirmed": "已确认, 正在同步登录态…", "expired": "二维码已过期, 正在换新码…",
             "error": "二维码创建失败, 正在重试…"}
    if state in table:
        return table[state]
    if state or raw:
        return "官方状态: %s%s" % (state or raw, ("(error_code=%s)" % code) if code else "")
    return "等待扫码…"


def _pick_nick(data):
    """从 /luna/me 的各种可能形态里抠昵称(字段名不稳定, 多路兜底)。"""
    for path in (("user", "nickname"), ("user", "nick_name"), ("user", "name"),
                 ("nickname",), ("account", "nickname"), ("data", "user", "nickname"),
                 ("data", "nickname")):
        cur = data
        for key in path:
            cur = cur.get(key) if isinstance(cur, dict) else None
        if isinstance(cur, str) and cur.strip():
            return cur.strip()[:24]
    return ""


def _me_info(cookie):
    """登录态探测 + 取昵称。匿名/失效回 `status_code=1000016`(返回 {} 表示网络失败)。"""
    if requests is None or not cookie:
        return {}
    try:
        resp = requests.post(
            API + QR_ME, params={"device_platform": "web"},
            data=json.dumps({}).encode("utf-8"),
            headers={"User-Agent": QR_UA, "Referer": API + "/", "Cookie": str(cookie),
                     "Content-Type": "application/json; charset=utf-8"}, timeout=15)
        data = resp.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _qr_digits(n):
    out = str(random.randint(1, 8))
    while len(out) < n:
        out += str(random.randint(0, 9))
    return out


def _qr_session():
    """扫码会话: device_id / install_id / msToken / verify_portrait 全程一致(官方按设备身份限流)。"""
    with _QR_LOCK:
        sess = _QR_STATE.get("session")
        if isinstance(sess, dict):
            return sess
        sess = {
            "device_id": _qr_digits(16), "install_id": _qr_digits(15),
            "ms_token": os.urandom(66).hex()[:88] + "==",
            "verify_portrait_id": "%s-%s-%s-%s-%s.login" % (
                _qr_digits(8), _qr_digits(4), _qr_digits(4), _qr_digits(4), _qr_digits(11)),
            "http": requests.Session() if requests is not None else None,
        }
        if sess["http"] is not None:
            sess["http"].headers.update({"User-Agent": QR_UA, "Referer": API + "/"})
        _QR_STATE["session"] = sess
        return sess


def _qr_params(sess, biz):
    """passport 公共参数(★全部走 query; aid=386088 是身份标识)。"""
    return {
        "passport_jssdk_version": "2.4.13", "passport_jssdk_type": "normal",
        "is_from_ttaccountsdk": "1", "aid": QR_AID, "language": "zh",
        "account_sdk_source": "web", "p_js_v": "2.4.13", "p_js_t": "pro",
        "p_zt": "3.3.5", "p_ver": "1.0.29", "request_host": "app%3A%2F%2Fresources",
        "p_bd": "1.0.0.41", "biz_trace_id": biz, "is_new_login": "1",
        "is_from_iesaccountsaas": "1", "device_id": sess["device_id"],
        "install_id": sess["install_id"], "did": sess["device_id"],
        "iid": sess["install_id"], "device_platform": "PC", "version_code": "3.5.2",
        "account_sdk_source_info": "00", "msToken": sess["ms_token"],
    }


def _qr_call(sess, method, path, extra=None, body=None):
    """发一次 passport 请求 → (json, cookie 字符串)。"""
    http = sess.get("http") if isinstance(sess, dict) else None
    if http is None or requests is None:
        return {}, ""
    biz = "%08x" % random.getrandbits(32)
    params = _qr_params(sess, biz)
    params.update(extra or {})
    headers = {"Accept": "application/json, text/javascript", "User-Agent": QR_UA,
               "Referer": API + "/",
               "x-tt-passport-verify-portrait": sess["verify_portrait_id"],
               "x-tt-passport-trace-id": biz}
    data = None
    if body:
        data = urllib.parse.urlencode(body)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["x-ss-stub"] = hashlib.md5(data.encode("utf-8")).hexdigest().upper()
    try:
        if str(method).upper() == "GET":
            resp = http.get(API + path, params=params, headers=headers, timeout=20)
        else:
            resp = http.post(API + path, params=params, data=data, headers=headers, timeout=20)
        payload = resp.json()
    except Exception:
        return {}, _cookie_header(sess.get("http").cookies) if sess.get("http") is not None else ""
    return (payload if isinstance(payload, dict) else {}), _cookie_header(http.cookies)


def _qr_scan_url(token):
    """`light/invoke/scan_login` 形态链接 —— ⚠️ **不能用来完成授权**。

    上游 libresoda 的 `docs/QR-LOGIN.md` 实测记录: 这个形态"只上报 scanned,
    确认后永远停在 scanned", 即**确认落不了地**。这里保留它仅作"手机浏览器能打开"
    的兜底链接; **「App 授权登录」必须用官方下发的 `qrcode_index_url`**
    (见 `_qr_app_url()`) —— 上一版页面把它当成主按钮, 是个真 bug, 已修。
    """
    return "https://bff-pc.qishui.com/light/invoke/scan_login?" + urllib.parse.urlencode(
        {"token": str(token or ""), "os": "Android", "computer_name": "TVBox"})


def _qr_ensure(force=False):
    """确保有一个未过期的二维码 → (状态, 会话)。已创建且未过期就直接复用。"""
    fresh = False
    with _QR_LOCK:
        token = str(_QR_STATE.get("token") or "")
        expire = float(_QR_STATE.get("expire") or 0)
        if token and not force and time.time() < expire - 5:
            return str(_QR_STATE.get("status") or "new"), _QR_STATE.get("session")
        sess = _qr_session()
        sess["token"] = ""
        payload, cookies = _qr_call(sess, "GET", QR_GET,
                                    {"next": API, "need_logo": "false",
                                     "need_short_url": "false", "is_new_login": "1"})
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        tok = str(data.get("token") or "").strip()
        if not tok:
            _QR_STATE.update({"token": "", "status": "error", "png": b"", "expire": 0.0,
                              "desc": str(data.get("description") or payload.get("message")
                                          or "创建二维码失败")})
            return "error", sess
        png = b""
        raw = str(data.get("qrcode") or "")
        if raw.startswith("data:") and "," in raw:
            try:
                png = base64.b64decode(raw.split(",", 1)[1])
            except Exception:
                png = b""
        exp = float(data.get("expire_time") or 0)
        if exp < 1e9:                       # ★有的是「剩余秒数」有的是「绝对时刻」, 两种都兜
            exp = time.time() + (exp or QR_TTL)
        _QR_STATE.update({
            "session": sess, "token": tok, "png": png, "expire": exp,
            "qrcode_url": str(data.get("qrcode_index_url") or ""),
            "scan_url": _qr_scan_url(tok), "status": "new", "born": time.time(),
            "desc": str(data.get("web_name") or ""), "cookies": cookies,
            # 新码 = 新一轮: 清掉上一张码的诊断字段(否则页面会显示旧状态)
            "raw": "", "error_code": 0, "cool": 0.0, "limited": False, "verify": False,
        })
        fresh = True
    if fresh:
        _qr_watch_start()                   # 让状态推进不依赖页面是否开着
    return "new", sess


def _qr_check(deep=True):
    """轮询一次扫码状态 + 顺手收割宿主 WebView 的会话。返回状态快照(dict)。

    字段: status(规范化状态) / raw(官方原文) / error_code / ok / desc /
          limited(官方限流中) / verify(要二次验证) / src(Cookie 来源)。

    ★本轮三处关键修正(对应文件头「第十六轮」的根因清单):
      ① `error_code=7` 是**临时限流**: 不判失败, 也**不覆盖上一次状态**(否则「已扫码」会被
         打回「等待扫码」= 用户眼里的"状态不更新"); 冷却 5s, 交给后台线程继续;
      ② 状态词表补全, 陌生状态**原样透出**;
      ③ 成功判据不再只看响应体 —— 官方在响应体里**根本不给登录态**, 所以主判据是
         「宿主 WebView 的 Cookie 库里出现了会话字段」。
    """
    with _QR_LOCK:
        token = str(_QR_STATE.get("token") or "")
        sess = _QR_STATE.get("session")
        prev = str(_QR_STATE.get("status") or "")
    if not token or not isinstance(sess, dict):
        if _login_cookie():
            return {"status": "confirmed", "raw": "", "error_code": 0, "ok": True,
                    "desc": "已登录", "limited": False, "verify": False, "src": "本地"}
        return {"status": "", "raw": "", "error_code": 0, "ok": False, "desc": "尚未生成二维码",
                "limited": False, "verify": False, "src": ""}
    body = {"need_logo": "false", "need_short_url": "false", "is_frontier": "true",
            "token": token, "is_new_login": "1", "next": API}
    payload, cookies = _qr_call(sess, "POST", QR_CHECK, {}, body)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if not data:
        data = payload if isinstance(payload, dict) else {}       # 有的形态状态挂顶层
    raw = str(data.get("status") or "").strip()
    code = int(data.get("error_code") or 0)
    desc = str(data.get("description") or payload.get("message") or "")
    limited = code == 7
    verify = code == 2046
    status = _qr_norm(raw, code)
    if limited or verify:
        status = prev or status                 # 限流/二次验证: 既不推进也不回退状态
    if status == "confirmed":
        redir = str(data.get("redirect_url") or data.get("desc_url") or "").strip()
        if redir.startswith(("http://", "https://")):
            cookies = _cookie_merge(cookies, _qr_follow(redir, sess))
    with _QR_LOCK:
        if cookies:
            _QR_STATE["cookies"] = _cookie_merge(_QR_STATE.get("cookies"), cookies)
        if status:
            _QR_STATE["status"] = status
        _QR_STATE["raw"] = raw
        _QR_STATE["error_code"] = code
        _QR_STATE["limited"] = limited
        _QR_STATE["verify"] = verify
        _QR_STATE["cool"] = (time.time() + _QR_COOL) if limited else 0.0
        if desc:
            _QR_STATE["desc"] = desc
        jar = str(_QR_STATE.get("cookies") or "")
    ok, src = False, ""
    if _qr_cookie_ok(jar):
        ok, src = True, "直连"
    elif _login_host_sync():                    # ★主判据: 宿主 WebView 里的官方会话
        ok, src = True, "宿主WebView"
    if not ok:
        reject = str(_HOST_STATE.get("reject") or "")
        if reject:
            desc = reject                       # 如实告诉用户「为什么没收下这份会话」
    if ok:
        with _QR_LOCK:
            _QR_STATE["status"] = "confirmed"
            _QR_STATE["src"] = src
            cookie = str(_QR_STATE.get("cookies") or "")
        _login_save(cookie)
        info = _me_info(cookie)
        if info and int(info.get("status_code") or 0) == 1000016:
            # 官方明确说这份 Cookie 无效 → 不留一份假登录态(否则后面取数会一直失败)
            _login_forget()
            ok, src = False, ""
            desc = "官方回「登录状态已失效」(status_code=1000016), 这份 Cookie 没落地"
        else:
            nick = _pick_nick(info) if info else ""
            if nick:
                _login_save(cookie, nick=nick)
    with _QR_LOCK:
        if not ok:
            _QR_STATE["src"] = ""
        final = str(_QR_STATE.get("status") or status)
    return {"status": final, "raw": raw, "error_code": code, "ok": ok, "desc": desc,
            "limited": limited, "verify": verify, "src": src}


# ------------------------------------------------------- 宿主 WebView 会话收割
_JAVA_STATE = {"ok": None, "miss_at": 0.0}


def _java_ready():
    """chaquopy 的 Java 互操作是否可用。

    ★带 60s 负缓存: 后台守护线程每 3s 就会来收一次 Cookie, 在**非 webhtv 宿主**(没有 chaquopy)
    上不能每次都对 `import java` 白试一遍。
    """
    if _JAVA_STATE["ok"] is True:
        return True
    if _JAVA_STATE["ok"] is False and time.time() - float(_JAVA_STATE["miss_at"] or 0) < 60:
        return False
    try:
        import java  # noqa: F401
        _JAVA_STATE["ok"] = True
    except Exception:
        _JAVA_STATE["ok"] = False
        _JAVA_STATE["miss_at"] = time.time()
    return bool(_JAVA_STATE["ok"])


def _host_data_dir():
    """App 私有数据目录(`/data/data/<pkg>`)。走 chaquopy 的 Java 互操作。

    `com.fongmi.android.tv.App.get()` 是 public static(App.java:61) → 拿 Application →
    `getApplicationInfo().dataDir`。拿不到就退环境变量, 再不行返回空串(功能自动降级)。
    """
    if not _java_ready():
        return ""
    try:
        from java import jclass
        app = jclass("com.fongmi.android.tv.App").get()
        if app is not None:
            return str(app.getApplicationInfo().dataDir or "")
    except Exception:
        pass
    for key in ("ANDROID_PRIVATE", "ANDROID_APP_DATA"):
        path = os.environ.get(key)
        if path and os.path.isdir(path):
            return path
    return ""


def _host_cookie_java(url):
    """`CookieManager.getInstance().getCookie(url)` —— 首选读法。

    App 自己就在**后台线程**这么读(`web/CookieBridge.java:13` 被 `WebHomeRawAdapter` /
    `WebHomeInlineVodStore` 调用, 见文件头第十六轮), 所以这里从后台线程读同样安全。
    """
    if not _java_ready():
        return ""
    try:
        from java import jclass
        manager = jclass("android.webkit.CookieManager").getInstance()
        return str(manager.getCookie(str(url)) or "")
    except Exception:
        return ""


def _host_cookie_sqlite():
    """退路: 直读 WebView 的 Cookie SQLite(`app_webview/**/Cookies`)。

    只在 Java 互操作不可用时才走。库可能被 WebView 占用 → **先复制再读**;
    只取 qishui.com / douyin.com 这两个域的 Cookie, 免得把别的网页的 Cookie 也塞进来。
    """
    if not _java_ready():
        return ""
    try:
        import glob
        import shutil
        import sqlite3
    except Exception:
        return ""
    data_dir = _host_data_dir()
    if not data_dir:
        return ""
    names = ("app_webview/Default/Cookies", "app_webview/default/Cookies",
             "app_webview/Default/Network/Cookies", "app_webview/default/network/Cookies",
             "app_hws_webview/default/Cookies")
    cands = [os.path.join(data_dir, n) for n in names]
    cands += glob.glob(os.path.join(data_dir, "app_webview", "*", "*Cookies"))
    out, seen = {}, set()
    for src in cands:
        if not os.path.isfile(src) or src in seen:
            continue
        seen.add(src)
        tmp = os.path.join(tempfile.gettempdir(), "qs_wvcookie_%d.db" % abs(hash(src)))
        try:
            shutil.copyfile(src, tmp)          # 被占用时直接读会报 database is locked
            conn = sqlite3.connect(tmp)
            rows = conn.execute("select host_key, name, value from cookies").fetchall()
            conn.close()
        except Exception:
            continue
        finally:
            try:
                os.remove(tmp)
            except Exception:
                pass
        for host, name, value in rows:
            host = str(host or "").lower()
            if not (host.endswith("qishui.com") or host.endswith("douyin.com")):
                continue
            name, value = str(name or ""), str(value or "")
            if name and value and name not in out:
                out[name] = value
    return _cookie_str(out)


def _host_cookie(force=False):
    """宿主 WebView 里与汽水/抖音相关的 Cookie(合并 Java 与 SQLite 两条读法)。"""
    with _HOST_LOCK:
        now = time.time()
        if not force and now - float(_HOST_STATE.get("checked") or 0) < HOST_COOKIE_TTL:
            return str(_HOST_STATE.get("cookie") or "")
    text = ""
    if _LOGIN_HOST_ON:
        for url in HOST_COOKIE_URLS:
            text = _cookie_merge(text, _host_cookie_java(url))
        if not _qr_cookie_ok(text):
            text = _cookie_merge(text, _host_cookie_sqlite())
    with _HOST_LOCK:
        _HOST_STATE["cookie"] = text
        _HOST_STATE["checked"] = now
    return text


def _login_host_sync(force=False):
    """从宿主 WebView 收割登录态 → `/luna/me` 校验 → 落盘。返回 True 表示已登录。

    ★这是「手机确认登录后这边更新状态」的正面回答: 官方确认后**响应体里没有登录态**,
    但宿主的 WebView 里有官方会话 —— 源与宿主同进程同 uid, 直接去取。
    """
    if _login_cookie():
        return True
    with _HOST_LOCK:
        _HOST_STATE["reject"] = ""
    host = _host_cookie(force=force)
    if not _qr_cookie_ok(host):
        return False
    info = _me_info(host)
    if int((info or {}).get("status_code") or 0) == 1000016:
        with _HOST_LOCK:
            _HOST_STATE["reject"] = ("宿主里的会话被官方判为已失效(status_code=1000016) —— "
                                     "请在弹出窗口里重新登录一次")
        return False                            # 会话不完整/已失效 → 不落盘
    _login_save(host, nick=_pick_nick(info) if info else "")
    with _QR_LOCK:
        _QR_STATE["status"] = "confirmed"
        _QR_STATE["src"] = "宿主WebView"
        _QR_STATE["cookies"] = _cookie_merge(_QR_STATE.get("cookies"), host)
    return True


def _login_toast_done():
    """登录成功后弹一个本地「✅ 登录成功」窗口(宿主可用且开关打开时; 只弹一次)。"""
    if not _LOGIN_TOAST:
        return False
    with _QR_LOCK:
        if _QR_STATE.get("done_pop"):
            return False
        _QR_STATE["done_pop"] = True
    local = _login_origin()[0]
    if not local:
        return False
    return _app_open_window(local + "/login?mode=done")


def _qr_watch_start():
    """启动后台登录守护线程(幂等)。

    ★这是「状态一定会更新」的落地方式: 状态推进不再依赖登录页的 AJAX 是否还开着 ——
    页面关掉、切到别的分类, 状态照样在推进, 成功照样落盘。
    """
    if not _LOGIN_WATCH_ON:
        return
    with _QR_LOCK:
        th = _QR_WATCH.get("thread")
        if th is not None and th.is_alive():
            return
        th = threading.Thread(target=_qr_watch_loop, name="qs-login-watch", daemon=True)
        _QR_WATCH["thread"] = th
    th.start()


def _qr_watch_loop():
    """★守护轮询循环: 每 3s(限流时 5s)推进一次状态; 二维码过期自动换新; 成功即落盘并弹窗。"""
    rounds = 0
    try:
        while rounds < _QR_WATCH_MAX:
            rounds += 1
            with _QR_LOCK:
                token = str(_QR_STATE.get("token") or "")
                expire = float(_QR_STATE.get("expire") or 0)
            if not token or _login_cookie():
                break
            if time.time() > expire:
                try:
                    _qr_ensure(force=True)      # 官方码只有 ~90s(expire_time), 自动换新
                except Exception:
                    pass
                time.sleep(_QR_POLL)
                continue
            result = {}
            try:
                result = _qr_check()
            except Exception:
                result = {}
            if result.get("ok"):
                _login_toast_done()
                break
            wait = _QR_COOL + 0.5 if result.get("limited") else _QR_POLL
            time.sleep(max(1.0, min(wait, 12.0)))
    except Exception:
        pass
    finally:
        with _QR_LOCK:
            _QR_WATCH["thread"] = None


def _lan_ip():
    """本机局域网 IP(给手机打开 /login 用)。"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("223.5.5.5", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return ""


def _start_login_server():
    """登录服务: **监听 0.0.0.0**(手机要能开 /login); 复用音频服务那个 handler 类。"""
    with _QR_LOCK:
        if _QR_STATE.get("port"):
            return int(_QR_STATE["port"])
    for port in range(QR_PORT_RANGE[0], QR_PORT_RANGE[1]):
        try:
            server = ThreadingHTTPServer(("0.0.0.0", port), _AudioHandler)
        except Exception:
            continue
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        with _QR_LOCK:
            _QR_STATE["port"] = port
            _QR_STATE["server"] = server
        return port
    return 0


def _login_origin():
    """→ (本机地址, 局域网地址)。分别给 TVBox 客户端与手机用。"""
    if not _LOGIN_ENABLED:
        return "", ""
    port = _start_login_server()
    if not port:
        return "", ""
    local = "http://127.0.0.1:%d" % port
    ip = _lan_ip()
    lan = ("http://%s:%d" % (ip, port)) if ip and ip != "127.0.0.1" else ""
    return local, lan


def _app_probe_port():
    """探测宿主(webhtv)本地 HTTP 服务端口 → 0 = 不可用(非此 App / 服务未起)。

    判别请求用 `/device`: `Nano.serve` 对它特判, 直接回 `Device.get().toString()`
    的 JSON(含 `"name"` 字段), 比"回 200 就算"可靠得多。

    性能: 9978 是 `Server.start()` 第一个候选, 命中率最高 → 先单点试; 不中才并发扫
    其余端口(0.35s 超时, 总开销从最坏 7s 压到 ~0.4s)。结果带缓存(命中 300s /
    未命中 20s), 不会每点一次卡片都扫一遍。
    """
    if requests is None:
        return 0
    now = time.time()
    with _APP_LOCK:
        port = int(_APP_STATE.get("port") or 0)
        checked = float(_APP_STATE.get("checked") or 0)
        if port and now - checked < APP_PORT_TTL:
            return port
        if not port and now - checked < APP_PORT_MISS_TTL:
            return 0
    hit = {"port": 0}
    lock = threading.Lock()

    def probe(p):
        if hit["port"]:
            return
        try:
            resp = requests.get("http://127.0.0.1:%d%s" % (p, APP_DEVICE), timeout=0.35)
            if resp.status_code == 200 and '"name"' in (resp.text or "")[:600]:
                with lock:
                    if not hit["port"]:
                        hit["port"] = p
        except Exception:
            pass

    probe(APP_PORT_RANGE[0])
    if not hit["port"]:
        threads = [threading.Thread(target=probe, args=(p,), daemon=True)
                   for p in range(APP_PORT_RANGE[0] + 1, APP_PORT_RANGE[1])]
        for t in threads:
            t.start()
        for t in threads:
            t.join(1.0)
    with _APP_LOCK:
        _APP_STATE["port"] = int(hit["port"] or 0)
        _APP_STATE["checked"] = time.time()
    return int(hit["port"] or 0)


def _app_call(path, payload, timeout=3.0):
    """POST 一次宿主本地服务 → HTTP 状态码; 不可达返回 None。"""
    port = _app_probe_port()
    if not port or requests is None:
        return None
    try:
        resp = requests.post(
            "http://127.0.0.1:%d%s" % (port, path),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=timeout)
        return int(resp.status_code)
    except Exception:
        return None


def _app_open_window(url):
    """让宿主**弹出内嵌 WebView 窗口**(`/msg` → `openInternalWebview`)。

    成功后宿主会顺手 post `CatWebEvent` 让详情页立刻退场 —— 用户看到的就是
    「点卡片 → 直接弹窗」, 不会先闪一个空白详情页。

    ★ 只接受 http(s): 内嵌页把非 http(s) 的 scheme 一律丢弃(见常量区事实清单),
    传 scheme 过去纯属浪费一次调用, 不如省下来直接走文案兜底。
    """
    if not _APP_WINDOW or not url:
        return False
    if not str(url).startswith(("http://", "https://")):
        return False
    return _app_call(APP_MSG, {"action": "openInternalWebview",
                               "opt": {"url": str(url)}}) is not None


def _qr_app_url():
    """官方「打开 App 授权」深链 = `data.qrcode_index_url`(实测是 https)。

    ★与 `_qr_scan_url()` 的区别(这正是一个真 bug 的修复):
      历史版本页面上那个「打开汽水音乐 App」按钮指向 `light/invoke/scan_login`,
      而上游 docs/QR-LOGIN.md 实测记录该形态"只上报 scanned, 确认后永远停在 scanned"
      → 点它授权**落不了地**。官方真正给的是 `qrcode_index_url`
      (`/ucenter_web/app/sdk-next?…&uc_sdk=scan-auth`), 它才是能在手机上唤起 App
      并完成确认的入口。
    """
    url = str(_QR_STATE.get("qrcode_url") or "").strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return ""


def _qr_status_json():
    """给登录页 AJAX 用的状态快照(**纯读缓存**, 不在这里打官方接口)。

    ★轮询已经搬到后台守护线程 `_qr_watch_loop`(第十六轮):
      · 页面每 3s 只读一次快照 → 状态一定是最新的, 且页面刷多快都不会把自己限流掉;
      · 页面关掉/切走, 状态照样推进(旧实现只挂在这儿, 页面一关就断, 正是"状态不更新"的一半原因)。
    线程不在(首次进入 / 异常退出)时这里补一次, 并顺手从宿主 WebView 收一次会话。
    """
    with _QR_LOCK:
        has_token = bool(_QR_STATE.get("token"))
        due = (time.time() - float(_QR_STATE.get("polled") or 0)) >= 2.5
    thread = _QR_WATCH.get("thread")
    if _LOGIN_WATCH_ON and has_token:
        if thread is None or not thread.is_alive():
            _qr_watch_start()
    elif due:
        # 守护线程被关掉时的旧行为: 这里按 ≥2.5s 的最小间隔打一次
        with _QR_LOCK:
            _QR_STATE["polled"] = time.time()
        try:
            _qr_check()
        except Exception:
            pass
    if not has_token:
        _login_host_sync()                  # 没有活码: 也允许直接从宿主 WebView 收登录态
    with _QR_LOCK:
        state = str(_QR_STATE.get("status") or "")
        raw = str(_QR_STATE.get("raw") or "")
        code = int(_QR_STATE.get("error_code") or 0)
        limited = bool(_QR_STATE.get("limited"))
        verify = bool(_QR_STATE.get("verify"))
        src = str(_QR_STATE.get("src") or "")
        desc = str(_QR_STATE.get("desc") or "")
        expire = max(0, int(float(_QR_STATE.get("expire") or 0) - time.time()))
    nick = str((_login_load() or {}).get("nick") or "")
    ok = bool(_login_cookie())
    if ok:
        tip = "✅ 登录成功" + (("：" + nick) if nick else "") + " · 按返回键即可"
    else:
        tip = _qr_tip(state, raw, limited, verify, code)
    return {"status": state, "ok": ok, "nick": nick, "tip": tip, "expire": expire,
            "raw": raw, "error_code": code, "limited": limited, "verify": verify,
            "src": src, "detail": desc[:60], "app": bool(_qr_app_url())}


def _login_done_html():
    """登录成功页: 后台线程从宿主 WebView 收到会话后弹出来, 给一个明确的「这边也更新了」反馈。"""
    with _QR_LOCK:
        src = str(_QR_STATE.get("src") or "")
    nick = str((_login_load() or {}).get("nick") or "") or "汽水用户"
    src_note = ("会话来源：%s" % src) if src else ""
    return ("""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>汽水音乐 · 登录成功</title>
<style>
 body{margin:0;padding:8vh 20px;background:#0f1712;color:#e8eaed;text-align:center;
      font:16px/1.75 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
 h1{font-size:clamp(22px,3vh,32px);color:#39d353;margin:0 0 12px}
 p{color:#9aa4ad;font-size:clamp(13px,1.9vh,17px)}
 b{color:#cfd3da}
 small{color:#5d666e;font-size:clamp(11px,1.5vh,13px)}
</style></head><body>
<h1>✅ 登录成功</h1>
<p>已登录 <b>__NICK__</b>，登录态已保存到本机。</p>
<p>请按 <b>返回键</b> 回到 TVBox：「登录」分类会显示「已登录」，<br>
听歌模式此后按 <b>官方 App 模式</b> 取数。</p>
<p><small>__SRC__</small></p>
</body></html>""").replace("__NICK__", nick).replace("__SRC__", src_note)


def _login_html(mode="qr", state=""):
    """登录引导页: 官方二维码 + 实时状态(AJAX, 不闪屏) + 「打开汽水音乐 App 授权」入口。

    `mode="app"`(App 授权登录) 把官方授权深链提到最显眼处; `mode="qr"`(扫码登录)
    以二维码为主。两种模式共用同一张官方码 —— 区别只在"谁来扫": 另一台手机扫 =
    扫码登录; 在本机/手机点链接 = App 授权登录。

    ★ 主按钮指向官方 `qrcode_index_url`(https)。**手机上**打开它会经 App Links
    直接唤起汽水音乐 App; 在**本机内嵌 WebView** 里打开则是官方授权页正常渲染
    (页内再跳 App 会被宿主拦, 见常量区事实清单, 源侧无解)。

    ★(第十六轮) 状态由**后台守护线程**推进, 本页每 3s 只读一次快照 ⇒ 页面一关状态也照样
    在走; 同时页面底部会显示**官方原文**(status / error_code / 会话来源), 所以「状态有没有
    变化」是看得见的, 不再出现"手机上都确认了这里还写等待扫码"。
    """
    mode = str(mode or "").lower()
    if mode == "done" or _login_cookie():
        return _login_done_html()
    mode = "app" if mode.startswith("app") else "qr"
    with _QR_LOCK:
        raw = str(_QR_STATE.get("raw") or "")
        code = int(_QR_STATE.get("error_code") or 0)
        limited = bool(_QR_STATE.get("limited"))
        verify = bool(_QR_STATE.get("verify"))
    app_url = _qr_app_url()
    link = app_url or str(_QR_STATE.get("scan_url") or "")
    tip = _qr_tip(str(state or ""), raw, limited, verify, code)
    diag = ("官方返回：status=%s%s" % (raw or "-", (" · error_code=%d" % code) if code else ""))
    title = "打开汽水音乐 App 完成授权" if mode == "app" else "扫码登录"
    if mode == "app" and app_url:
        lead = ("点下面按钮 → <b>手机上会直接唤起汽水音乐 App</b> 完成授权；"
                "也可以直接用手机扫下面的码。")
    else:
        lead = "用手机「抖音 App → 扫一扫」扫下面的码，然后在手机上点「确认」。"
    qr_url = "/qr?t=%d" % int(time.time())
    link_attr = str(link or "#").replace("&", "&amp;").replace('"', "&quot;")
    return """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>汽水音乐 · 登录</title>
<style>
 *{box-sizing:border-box}
 body{margin:0;padding:3vh 16px;background:#101216;color:#e8eaed;
      font:16px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
      text-align:center;-webkit-user-select:none;user-select:none}
 h1{font-size:clamp(19px,2.6vh,26px);margin:0 0 6px;font-weight:600}
 .tip{color:#ffd166;font-size:clamp(14px,1.9vh,18px);min-height:1.6em;margin:8px 0 14px}
 body.ok .tip{color:#39d353;font-weight:600}
 .box{background:#fff;border-radius:14px;padding:14px;display:inline-block;
      box-shadow:0 8px 28px rgba(0,0,0,.45)}
 .box img{display:block;width:min(52vh,320px);height:auto}
 a.btn{display:block;max-width:420px;margin:16px auto 0;padding:clamp(12px,1.7vh,16px) 18px;
       border-radius:11px;background:#1e88ff;color:#fff;text-decoration:none;font-weight:600;
       font-size:clamp(15px,2vh,18px)}
 a.btn:focus,a.btn:hover{background:#3d9bff;outline:3px solid #8fd694;outline-offset:2px}
 a.alt{background:#242832;color:#c9cdd4;font-weight:500}
 p.note{color:#8b909a;font-size:clamp(12px,1.6vh,14px);max-width:460px;margin:18px auto 0;text-align:left}
 p.diag{color:#5d666e;font-size:clamp(11px,1.5vh,13px);max-width:460px;margin:10px auto 0}
 b{color:#cfd3da}
 #lnk{position:absolute;left:-9999px;top:0;opacity:0}
</style></head><body class="__OK__">
<h1>__TITLE__</h1>
<div class="tip" id="tip">__TIP__</div>
<div class="box"><img src="__QR__" alt="二维码"></div>
<a class="btn" href="__LINK__">① 打开汽水音乐 App 完成授权</a>
<a class="btn alt" href="javascript:location.reload()">② 刷新状态</a>__COPYBTN__
<input id="lnk" type="text" value="__LINK__" readonly tabindex="-1">
<p class="note">__LEAD__<br>
扫码后本页会<b>自动</b>变成「✅ 登录成功」，不需要手动刷新；成功后按返回键回到 TVBox，
重进「登录」分类即为「已登录」。<br>
<b>本页关掉也没关系</b>：状态在后台继续推进，登录成功后会自动弹一个「✅ 登录成功」窗口。</p>
<p class="diag" id="diag">__DIAG__</p>
<script>
function tick(){
  fetch('/login/status',{cache:'no-store'}).then(function(r){return r.json()}).then(function(d){
    document.getElementById('tip').textContent=d.tip||'';
    var diag='';
    if(d.raw){diag='官方返回: status='+d.raw+(d.error_code?(' · error_code='+d.error_code):'')+(d.src?(' · 会话来源: '+d.src):'');}
    document.getElementById('diag').textContent=diag;
    if(d.ok){document.body.className='ok';clearInterval(timer);return}
    if(d.limited){return}
    if(!d.expire||d.status==='expired'){location.reload()}
  }).catch(function(){});
}
function copyLink(){
  var el=document.getElementById('lnk'),tip=document.getElementById('tip');
  try{el.select();document.execCommand('copy');tip.textContent='✅ 链接已复制, 粘到手机浏览器打开即可拉起 App';}
  catch(e){tip.textContent='复制失败, 请长按上方按钮手动复制链接';}
}
var timer=setInterval(tick,3000);
</script>
</body></html>"""\
        .replace("__OK__", "") \
        .replace("__TITLE__", title) \
        .replace("__TIP__", tip) \
        .replace("__QR__", qr_url) \
        .replace("__LINK__", link_attr) \
        .replace("__DIAG__", diag) \
        .replace("__COPYBTN__", (
            '\n<a class="btn alt" href="javascript:copyLink()">'
            '③ 复制授权链接（粘到手机浏览器可直接拉起 App）</a>' if link else "")) \
        .replace("__LEAD__", lead)


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

    def _serve_qr(self):
        """把官方下发的二维码 PNG(data:image/png;base64)原样吐给客户端/浏览器。"""
        png = _QR_STATE.get("png") or b""
        if not png:
            self._fail(404, b"no qrcode")
            return
        try:
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(png)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(png)
        except OSError:
            self.close_connection = True

    def _serve_login(self):
        """登录引导页(手机浏览器打开 / 宿主内嵌窗口打开 都用它)。

        `?mode=app` 走「App 授权登录」形态(突出官方授权深链), 缺省 `qr` 走扫码形态。
        """
        try:
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            mode = str((query.get("mode") or ["qr"])[0] or "qr")
            _qr_ensure()
            html = _login_html(mode, str(_QR_STATE.get("status") or "")).encode("utf-8")
        except Exception:
            html = "<h1>登录服务异常</h1>".encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(html)
        except OSError:
            self.close_connection = True

    def _serve_login_status(self):
        """`/login/status` → 状态 JSON(给登录页 AJAX 用, 免得整页 reload 闪屏)。"""
        try:
            body = json.dumps(_qr_status_json(), ensure_ascii=False).encode("utf-8")
        except Exception:
            body = b'{"status":"","ok":false,"tip":"","expire":0}'
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except OSError:
            self.close_connection = True

    def _serve(self, body):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/qr"):              # 登录二维码(官方 PNG)
            return self._serve_qr()
        if path.startswith("/login/status"):    # ★必须排在 /login 之前, 否则被它吞掉
            return self._serve_login_status()
        if path == "/login" or path.startswith("/login"):   # 登录引导页(手机/宿主内嵌窗口)
            return self._serve_login()
        name = path.rsplit("/", 1)[-1]
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
        self._anon = None
        self._kuwo_sess = None
        self._cfg = {}

    def init(self, extend=""):
        global _LOGIN_ENABLED, _APP_WINDOW, _LOGIN_WATCH_ON, _LOGIN_HOST_ON, _LOGIN_TOAST
        try:
            self._cfg = json.loads(extend) if (isinstance(extend, str) and extend.strip()) else extend
        except Exception:
            self._cfg = {}
        if not isinstance(self._cfg, dict):
            self._cfg = {}
        # 登录服务(0.0.0.0 上的二维码/引导页)是否启用; 关掉不影响「手动 Cookie 通道」
        _LOGIN_ENABLED = self._flag("login", True) and self._flag("login_server", True)
        # 是否调宿主(webhtv)的 /msg 弹内嵌窗口; 关掉后登录卡片退回「详情页文案」模式
        _APP_WINDOW = self._flag("app_window", True)
        # ★第十六轮: 后台登录守护线程(状态推进不依赖页面是否开着)
        _LOGIN_WATCH_ON = self._flag("login_watch", True)
        # 读宿主 WebView 的 Cookie(登录态真正来源; 见文件头第十六轮)
        _LOGIN_HOST_ON = self._flag("login_host", True)
        # 登录成功后弹「✅ 登录成功」窗口
        _LOGIN_TOAST = self._flag("login_toast", True)

    def getName(self):
        return "汽水音乐"

    # ------------------------------------------------------------------ HTTP
    @staticmethod
    def _new_session():
        s = requests.Session()
        s.headers.update({
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://music.douyin.com/",
        })
        return s

    def _session(self, auth=True):
        """HTTP 会话。

        auth=True → 带登录 Cookie: 登录态下服务端才认 `scene_mode_id` / `mode`
        (匿名请求对这两个参数**零过滤**, 见文件头第十一/十二轮)。
        auth=False → 匿名会话: **取流(`seo_track`)固定走它** —— 保持与「没登录时的现在
        模式」逐字节一致, 免得登录后官方改发加密/VIP 流反而播不了。
        """
        if not auth:
            if self._anon is None:
                self._anon = self._new_session()
            return self._anon
        if self._sess is None:
            self._sess = self._new_session()
        cookie = _login_cookie()
        if cookie:
            if self._sess.headers.get("Cookie") != cookie:
                self._sess.headers["Cookie"] = cookie
        elif "Cookie" in self._sess.headers:
            self._sess.headers.pop("Cookie", None)
        return self._sess

    def _req(self, path, body=None, query=None, auth=True):
        """统一请求: GET(query) / POST(body) 都返回 dict, 失败返回 {}"""
        if requests is None:
            return {}
        url = API + path
        try:
            sess = self._session(auth)
            if body is None:
                r = sess.get(url, params=query or None, timeout=18)
            else:
                r = sess.post(
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
        if self._flag("login", True):
            classes.append({"type_id": "login", "type_name": "登录"})   # ★排在最末
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
            if str(tid) == "login":
                return self._login_cards(page)
            return self._listen(self._extend(extend, "cate", "推荐"), page)
        except Exception:
            return self._result([], page)

    # ------------------------------------------------------------------ 登录
    # ★需求原文(第十三轮): 「分类最后加登录, 分扫码登录 / 手动拉起官方 app 授权登录;
    #             没登录按现在模式, 登录后按官方 app 模式获取」。
    #   实现要点: TVBox 没有交互界面 → 卡片封面(vod_pic)指向本机 `/qr`(转发官方二维码);
    #   ★**点卡片那一刻**(第十五轮)由源直接调宿主 `/msg` 弹出**内嵌 WebView 窗口**,
    #   窗口里是官方二维码 + AJAX 实时状态, 登录成功自动变绿。宿主不可用时(非 webhtv /
    #   服务未起)逐字回落到原来的「详情页文案 + 手动刷新」链路, 行为与上一版一致。
    def _login_cards(self, page):
        """「登录」分类: 未登录 → 「扫码登录」+「App 授权登录」; 已登录 → 状态 + 退出。

        两张卡都**点一下就弹窗**(宿主可用时), 不需要再"点开-刷新-再点开"。"""
        if _login_cookie():
            self._login_verify()                    # 顺手校验(明确失效才清, 网络抖动不动它)
        if not _login_cookie():
            # ★宿主 WebView 里可能已经有官方会话(用户在弹出窗口里登录过 / 用过官方网页登录)
            #   → 进列表就先同步一次, 这样「登录成功了」会立刻反映成「已登录」卡片。
            try:
                _login_host_sync(force=True)
            except Exception:
                pass
        if _login_cookie():
            state = _login_load()
            nick = str(state.get("nick") or "").strip() or "汽水用户"
            cards = [
                {"vod_id": self._pack("l", {"kind": "info"}), "vod_name": "已登录：" + nick,
                 "vod_pic": ICON, "vod_remarks": "点开查看账号 / 退出登录"},
                {"vod_id": self._pack("l", {"kind": "logout"}), "vod_name": "退出登录",
                 "vod_pic": ICON, "vod_remarks": "清除本机登录态, 回到匿名模式"},
            ]
            return self._result(cards, page, False, len(cards))
        status, local = "error", ""
        try:
            status, _sess = _qr_ensure()
            local, _lan = _login_origin()
        except Exception:
            pass
        pic = (local + "/qr?t=%d" % int(time.time())) if local else ICON
        remark = "点开弹出二维码" if status != "error" else "二维码创建失败, 返回重进"
        app_remark = "点开打开官方授权页" if _qr_app_url() else "点开弹出授权页"
        cards = [
            {"vod_id": self._pack("l", {"kind": "qr"}), "vod_name": "扫码登录",
             "vod_pic": pic, "vod_remarks": remark},
            {"vod_id": self._pack("l", {"kind": "app"}), "vod_name": "App 授权登录",
             "vod_pic": pic, "vod_remarks": app_remark},
        ]
        # ★第三张卡(第十六轮): 「网页登录」。理由很硬 —— 直连 passport 会被官方风控
        #   (`error_code=7`), 而且确认后的登录态**只在浏览器会话里**; 本机唯一有官方浏览器
        #   会话的地方就是宿主 WebView(`www.qishui.com` = 官方 Web 版, 登录走官方 JS 无风控)。
        #   在它里面登录完成后, 源直接读 WebView 的 Cookie 就拿到了会话 → 状态自动更新。
        if _APP_WINDOW and _LOGIN_HOST_ON and (_app_probe_port() or 0):
            cards.append({"vod_id": self._pack("l", {"kind": "web"}),
                          "vod_name": "网页登录（官方网页）", "vod_pic": ICON,
                          "vod_remarks": "在弹出窗口里登录, 成功后自动同步"})
        return self._result(cards, page, False, len(cards))

    @classmethod
    def _login_vod(cls, name, content):
        """登录相关卡片的详情页: 只给简介(不需要播放地址), 用户按提示返回刷新即可。"""
        return {"vod_id": cls._pack("l", {"kind": "info"}), "vod_name": str(name),
                "vod_pic": ICON, "vod_content": str(content),
                "vod_play_from": "汽水音乐", "vod_play_url": ""}

    def _login_verify(self):
        """用 `/luna/me` 校验登录态。

        ★只有在服务端**明确回 `status_code=1000016`(登录态已失效)**时才清除本地登录态;
        网络失败(返回 {})一律不动 —— 否则一次断网就会把用户的登录态误删。
        """
        cookie = _login_cookie()
        if not cookie:
            return False
        data = _me_info(cookie)
        if not data:
            return False
        if int(data.get("status_code") or 0) == 1000016:
            _login_forget()
            return False
        _login_save(cookie, nick=_pick_nick(data))
        return True

    def _login_detail(self, info):
        kind = str((info or {}).get("kind") or "info")
        if kind == "logout":
            _login_forget()
            return self._login_vod("已退出登录",
                                   "登录态已清除, 现在回到**匿名(现在模式)**取数。\n"
                                   "要重新登录: 返回「登录」分类。")
        if kind in ("qr", "app", "web"):
            # ★(第十六轮) 先把后台守护线程叫起来: 之后状态的推进与宿主会话的收割都不再
            #   依赖这个页面是否还开着 —— 这正是「手机确认后这边自动更新状态」的实现。
            try:
                _qr_watch_start()
            except Exception:
                pass
            # 宿主 WebView 里可能已经有官方会话(用户刚在弹出窗口里登录过) → 先同步一次
            try:
                if _login_host_sync(force=True):
                    nick = str(_login_load().get("nick") or "").strip() or "汽水用户"
                    return self._login_vod(
                        "✅ 登录成功：" + nick,
                        "登录态已保存到本机(来源: 宿主 WebView 官方会话)：%s\n\n"
                        "**返回上一页, 再进「登录」分类**即可看到「已登录」状态卡片。"
                        % _login_path())
            except Exception:
                pass
            state = "error"
            try:
                state, _sess = _qr_ensure()
            except Exception:
                pass
            # ★点卡片 = 直接弹窗(第十五轮): 宿主(webhtv)可用时立刻弹出内嵌 WebView
            #   窗口, 宿主顺手 post CatWebEvent 让本详情页退场 —— 用户看到的就是
            #   「点一下 → 窗口弹出来」, 不需要再手动刷新。宿主不可见时下面整段
            #   文案链路逐字保留, 行为与之前完全一致。
            local, lan = "", ""
            try:
                local, lan = _login_origin()
            except Exception:
                pass
            if kind == "qr":
                target = (local + "/login?mode=qr") if local else ""
            elif kind == "web":
                target = HOST_LOGIN_URL                       # 汽水官方 Web 版(第十六轮)
            else:
                target = _qr_app_url() or ((local + "/login?mode=app") if local else "")
            try:
                popped = _app_open_window(target)
            except Exception:
                popped = False
            name_of = {"qr": "扫码登录", "app": "App 授权登录", "web": "网页登录"}.get(kind, "登录")
            if popped:
                if kind == "web":
                    what = ("汽水**官方网页版** —— 在窗口里点「登录」完成登录（走官方 JS，"
                            "没有被直连风控的问题），登录成功后本机会**自动同步**登录态")
                elif kind == "app":
                    what = ("官方授权页 —— 用**手机**打开这条会直接唤起汽水音乐 App；"
                            "若在窗口里操作，就用另一台手机扫「扫码登录」的二维码并在 App 里确认")
                else:
                    what = "官方二维码 —— 用手机「抖音 App → 扫一扫」"
                return self._login_vod(
                    name_of + " · 已弹出窗口",
                    "已在屏幕上**弹出登录窗口**, 请在里面完成登录：\n\n"
                    "· 窗口里是%s；\n"
                    "· 完成后本机会**自动同步**登录态(状态在后台推进, 窗口关掉也算)，"
                    "并弹出一个「✅ 登录成功」窗口；\n"
                    "· 然后按返回键回到 TVBox, 重进「登录」分类即为「已登录」。\n\n"
                    "窗口没弹出来? 用手机浏览器打开: %s\n"
                    "（还不行就用搜索框粘 Cookie: `#登录 <Cookie>`；"
                    "在别的页面登录过也可以搜 `#取Cookie` 同步过来）"
                    % (what, lan or HOST_LOGIN_URL))
            result = {}
            try:
                result = _qr_check()
            except Exception:
                result = {}
            if result.get("ok") or _login_cookie():
                self._login_verify()
                nick = str(_login_load().get("nick") or "").strip() or "汽水用户"
                return self._login_vod(
                    "✅ 登录成功：" + nick,
                    "登录态已保存到本机：%s\n\n"
                    "**返回上一页, 再进「登录」分类**即可看到「已登录」状态卡片。\n"
                    "此后听歌模式会优先按**官方 App 模式流**取数(见文件头第十三轮)。"
                    % _login_path())
            status = str(result.get("status") or state or "")
            code = int(result.get("error_code") or 0)
            tip = _qr_tip(status, str(result.get("raw") or ""),
                          bool(result.get("limited")), bool(result.get("verify")), code)
            refreshed = False
            if code == 2 or status in ("expired", "expire", "timeout"):
                # 二维码过期(官方给的 expire_time 只有 ~90s): 立刻重建一张,
                # 用户**返回列表**就能看到新的码(封面每次都会重新拉 /qr)。
                try:
                    _qr_ensure(force=True)
                    refreshed = True
                except Exception:
                    refreshed = False
            if refreshed:
                tip = "二维码已过期, 已自动刷新 → 请返回列表重新扫码"
            extra = ""
            if code == 7:
                extra = ("\n⚠️ 官方临时限流(error_code=7) —— 这是**临时**的, 后台已在按 5s 冷却"
                         "自动重试, 请继续在手机上确认。")
            elif code == 2046:
                extra = ("\n⚠️ 官方要求二次安全验证(error_code=2046)。纯 HTTP 这一路做不了, "
                         "请改用「网页登录」或 `#登录 <Cookie>`。")
            elif code and not refreshed:
                extra += "\n(error_code=%s)" % code
            guide = ("　　2. 用手机浏览器/微信打开上面那条链接 → 会**直接唤起汽水音乐 App**, "
                     "在 App 内点「确认授权」。"
                     if kind == "app" else
                     "　　2. 用手机「抖音 App → 扫一扫」扫屏幕上的二维码, 然后在手机上点「确认」。")
            if kind == "web":
                guide = ("　　2. 在窗口里点页面上的「登录」→ 会走**官方登录**（扫码或账号密码）。\n"
                         "　　3. 登录完成后源会**自动**读取宿主 WebView 的官方会话并落盘。")
            if kind == "app":
                open_url = (lan + "/login?mode=app") if lan else (_qr_app_url() or "")
            elif kind == "web":
                open_url = HOST_LOGIN_URL
            else:
                open_url = (lan + "/login?mode=qr") if lan else ""
            body = ("当前状态：**%s**%s\n\n"
                    "%s\n"
                    "　1. 打开: %s\n"
                    "%s\n"
                    "② 状态由**后台线程**推进(页面关掉也算数), 成功后会自动弹「✅ 登录成功」；\n"
                    "　也可以**返回再进「登录」分类** → 已登录就会显示「已登录：昵称」。\n\n"
                    "③ 兜底通道(官方有风控时最可靠):\n"
                    "　· 搜索框输入 `#登录 <Cookie>` 手动粘贴(只要含 sessionid / sid_tt)；\n"
                    "　· 在别的页面/窗口里登录过 → 搜索框输入 `#取Cookie` 从宿主 WebView 同步过来。"
                    % (tip, extra, name_of + "（打开官方入口）",
                       open_url or "（本机登录页不可用, 请用下方通道）", guide))
            return self._login_vod(name_of + " · " + tip.split("·")[0].strip(), body)
        state = _login_load()
        if state.get("cookie"):
            nick = str(state.get("nick") or "").strip() or "汽水用户"
            return self._login_vod("已登录：" + nick,
                                   "已登录，当前按**官方 App 模式**取数(听歌模式优先走官方个性化模式流)。\n\n"
                                   "登录态文件：%s\n\n要退出请返回上一页点「退出登录」。" % _login_path())
        return self._login_vod("未登录",
                               "当前按**匿名(现在模式)**取数。\n返回上一页, 选「扫码登录」或「App 授权登录」。")

    def _login_command(self, text):
        """搜索框当输入通道: `#登录 <cookie>` / `#登录` / `#退出`（TVBox 唯一能打字的地方）。

        用途: 官方对**裸 HTTP 轮询**有风控(可能一路 error_code=7), 扫码拿不到 Cookie 时,
        用户可自己在浏览器里拿到 Cookie 粘贴进来 —— 这是最可靠的一条落地通路。
        """
        raw = str(text or "").strip()
        low = raw.lower()
        head, _, arg = raw.partition(" ")
        head_low = head.lower()
        if head_low not in ("#登录", "#login", "#退出", "#logout", "#登录状态", "#状态",
                           "#取cookie", "#取ck", "#同步", "#sync"):
            return None
        if head_low in ("#退出", "#logout"):
            _login_forget()
            return self._login_msg("已退出登录", "已清除本机登录态, 回到匿名模式")
        if head_low in ("#取cookie", "#取ck", "#同步", "#sync"):
            # ★(第十六轮) 从**宿主 WebView 的官方会话**里同步登录态 —— 用户在弹出窗口/官方网页
            #   里登录完, 一条命令就把登录态拉过来(这也是「登录成功后这边更新状态」的手动版)。
            ok = False
            try:
                ok = _login_host_sync(force=True)
            except Exception:
                ok = False
            if ok:
                nick = str((_login_load() or {}).get("nick") or "").strip()
                return self._login_msg(
                    "✅ 已同步宿主登录态" + (("：" + nick) if nick else ""),
                    "会话已落盘, 返回「登录」分类即为「已登录」")
            return self._login_msg(
                "⚠️ 没在宿主 WebView 里找到汽水会话",
                "先用「网页登录」在弹出窗口里登录; 或 `#登录 <Cookie>`")
        if head_low in ("#登录状态", "#状态"):
            state = _login_load()
            if state.get("cookie"):
                self._login_verify()
                state = _login_load()
            if not state.get("cookie"):
                try:
                    _login_host_sync(force=True)        # 顺手同步一次宿主会话
                except Exception:
                    pass
                state = _login_load()
            if state.get("cookie"):
                return self._login_msg("已登录：" + (str(state.get("nick") or "").strip() or "汽水用户"),
                                       "输入 `#退出` 可清除登录态")
            return self._login_msg("未登录", "在「登录」分类扫码, 或输入 `#登录 <Cookie>`")
        arg = str(arg or "").strip()
        if not arg:
            state = _login_load()
            if state.get("cookie"):
                return self._login_msg("已登录：" + (str(state.get("nick") or "").strip() or "汽水用户"),
                                       "输入 `#退出` 可清除登录态")
            return self._login_msg("未登录", "用法: 搜索 `#登录 <Cookie>`；扫码请看「登录」分类")
        cookie = self._norm_cookie(arg)
        if not _qr_cookie_ok(cookie):
            return self._login_msg("⚠️ Cookie 不完整",
                                   "里面没有 sessionid / sessionid_ss / sid_tt 之一, 请重新复制")
        _login_save(cookie)
        ok = self._login_verify()
        state = _login_load()
        if state.get("cookie"):
            nick = str(state.get("nick") or "").strip()
            head2 = "✅ 登录成功" + (("：" + nick) if (ok and nick) else "")
            note = "返回「登录」分类即可看到已登录状态" if ok else "已保存, 但未通过在线校验(可能已过期)"
            return self._login_msg(head2, note)
        return self._login_msg("⚠️ 登录态已失效", "官方回「登录状态已失效」, 请重新获取 Cookie")

    @staticmethod
    def _norm_cookie(text):
        """清洗粘贴的 Cookie: 去掉 `cookie:` 前缀 / 换行 / 首尾空白。"""
        raw = str(text or "").strip()
        raw = re.sub(r"^\s*cookie\s*:\s*", "", raw, flags=re.I)
        raw = raw.replace("\r", "").replace("\n", " ")
        return re.sub(r"\s+", " ", raw).strip().strip(";").strip()

    def _login_msg(self, name, note):
        """搜索通道的操作结果(以一条搜索结果的形式回显, 用户一眼能看到)。"""
        return self._result([{
            "vod_id": self._pack("l", {"kind": "info"}), "vod_name": str(name),
            "vod_pic": ICON, "vod_remarks": str(note)[:60]}], 1, False, 1)

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
        handled = self._login_command(keyword)      # `#登录 <Cookie>` / `#退出` / `#登录状态`
        if handled is not None:
            return handled
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
            login = self._unpack(value, "l")
            if login:
                return {"list": [self._login_detail(login)], "parse": 0, "jx": 0}
            track = self._unpack(value, "t")
            return {"list": [self._track_detail(track or value)], "parse": 0, "jx": 0}
        except Exception:
            return {"list": [{"vod_id": value, "vod_name": "汽水音乐", "vod_play_from": "汽水音乐",
                              "vod_play_url": "播放$a:" + value + ":auto"}], "parse": 0, "jx": 0}

    def _seo(self, track_id):
        # ★固定匿名(与「没登录」时的取流行为逐字节一致); 登录只影响内容类请求。
        return self._req("/luna/h5/seo_track", None,
                         {"track_id": str(track_id), "device_platform": "web"}, auth=False)

    def _req_url(self, url):
        if requests is None:
            return {}
        try:
            return self._session(False).get(url, timeout=18).json()
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

        ★听歌模式(preference / scene)走 `_feed_mode_tracks()`:
          按模式的中文主题词走**官方搜索接口**打底, 再用**官方中文榜单**(热歌榜/新歌榜)
          补足到 `mode_count`(默认 50) 首。
        ⚠️ 曾用过「官方 discover/mix 歌单池」, 但那个池子是按**流派**拼的(摇滚/电音/
          J-pop/indie/欧美民谣…), 且 `scene_mode_id` 对未登录请求零过滤 → 结果满屏
          **外文歌**(用户反馈「模式都变成英文歌了」)。已弃用, 详见 `_feed_mode_tracks`。
        ⚠️ 「欧美 / 日语 / k-pop」三个**语种模式**仍给外文内容(它们本来就该是外文歌)。
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
            tracks = self._feed_mode_tracks(mode=rid or "default",
                                            name=info.get("name"), want=want)
            if not tracks and rid == "familiar":        # 最后兜底: 怀旧电台
                tracks = self._radio_tracks(NOSTALGIA_RADIO, want)
        elif kind == "scene":
            tracks = self._feed_mode_tracks(scene_id=rid, name=info.get("name"), want=want)
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

    def _feed_mode_tracks(self, scene_id="", mode="", name="", want=50):
        """听歌模式曲目: 官方**主题搜索**打底 + 官方**中文榜单**补足, 去重凑 want 首。

        数据源与顺序(全部实测):
          ① **主题搜索** `POST /luna/search/track`, 关键词取 MODE_KEYWORDS(按模式名归一)。
             命中准且是中文: 粤语→灰色轨迹/傻女/富士山下, 国风→醉春烟/破阵曲,
             助眠→助眠轻音乐, 车载→中文经典老歌。约 1.0s / 20 首。
          ② **官方中文榜单**: 热歌榜(94% 中文, 50 首, 0.23s) / 新歌榜(86% 中文, 50 首)
             —— 「好听的中文歌」主要来自这里。TVBox 详情页不能翻页, 需要一次给足。
          ③ **官方推荐流** `POST /luna/pc/feed/song-tab`(每次 6 首, ~0.5s, 81% 中文)
             仅当①②仍不足时兜底。

        ⚠️ 「欧美 / 日语 / k-pop」这类**语种/地区模式**不掺中文榜单, 而是把①的关键词多翻
           2 页(它们本来就该是外文歌); 其余 45 个模式一律**中文优先**。

        ★为什么弃用 `discover/mix` 歌单池(上一版) —— 这是「模式都变成英文歌了」的根源:
          该池是按**流派**拼的(摇滚/电音/J-pop/indie/欧美民谣…), 抽到什么都看运气, 且
          `scene_mode_id` / `mode` 对未登录请求**零过滤**(同一场景连采样 4 次歌单集合
          零交集, 跨场景交集率与「完全不带场景」的基线相同 —— 官方场景专属流要登录态)。
          于是「模式里全是英文歌」。已弃用。
        """
        key = "s:%s|m:%s|n:%s|%d" % (scene_id, mode, name, want)
        now = time.time()
        hit = _MODE_TRACK_CACHE.get(key)
        if hit and now - hit[1] < _MODE_TRACK_TTL:
            return hit[0]

        # ★登录后 → 优先走**官方 App 模式流**(`scene_mode_id` / `mode` 这时服务端才认);
        #   拿不到内容则原样回落到下面的匿名策略 —— 所以「没登录=现在模式」不受影响。
        if _login_cookie():
            official = self._feed_official(scene_id, mode, want)
            if official:
                _MODE_TRACK_CACHE[key] = (official, now)
                return official

        mkey = _mode_key(name) or _mode_key(mode)
        kw = MODE_KEYWORDS.get(mkey, "")
        foreign = mkey in MODE_FOREIGN_KEYS
        tracks, seen = [], set()

        def add_many(objs, demote_junk=False):
            part = [self._track(x) for x in (objs or [])]
            part = [t for t in part if t and t.get("id")]
            if demote_junk:                             # 把「串烧/合集/DJ版」压到后面(不删)
                part.sort(key=lambda t: 1 if any(
                    j in str(t.get("name") or "") for j in MODE_JUNK) else 0)
            for t in part:
                tid = str(t.get("id"))
                if tid not in seen:
                    seen.add(tid)
                    tracks.append(t)

        # ① 主题搜索 —— 保证内容贴合该模式, 且(非语种模式时)是中文
        if kw:
            for page in range(1, 3 if foreign else 2):
                if len(tracks) >= want:
                    break
                try:
                    part = self._search_tracks(kw, page)
                except Exception:
                    part = []
                add_many(part, demote_junk=True)

        # ② 补足
        if len(tracks) < want:
            if foreign:                                 # 语种模式: 同词继续翻页
                for page in (3, 4):
                    if len(tracks) >= want:
                        break
                    try:
                        part = self._search_tracks(kw, page)
                    except Exception:
                        part = []
                    add_many(part, demote_junk=True)
            else:                                       # 其余模式: 官方中文榜单
                for _cname, cid in CHARTS:
                    if len(tracks) >= want:
                        break
                    try:
                        part = self._chart_tracks(cid)
                    except Exception:
                        part = []
                    add_many(part)

        # ③ 仍不足 → 官方推荐流(中文为主的随机流)
        rounds = 0
        while (not foreign) and len(tracks) < want and rounds < 4:
            rounds += 1
            try:
                data = self._req("/luna/pc/feed/song-tab", {
                    "played_media": [], "is_first_request": rounds == 1,
                    "is_did_first_request": rounds > 1,
                    "feed_counts": {"mix_session_count": rounds - 1}})
            except Exception:
                data = {}
            items = data.get("items") or []
            if not items:
                break
            add_many(items)

        tracks = tracks[:want]
        if tracks:
            _MODE_TRACK_CACHE[key] = (tracks, now)
            if len(_MODE_TRACK_CACHE) > 60:            # 简单清理, 防无界增长
                for k in list(_MODE_TRACK_CACHE)[:20]:
                    _MODE_TRACK_CACHE.pop(k, None)
        return tracks

    def _feed_official(self, scene_id="", mode="", want=50):
        """★登录后: 走**官方 App 的模式流**(第13轮)。拿不到就返回 [] → 调用方回落匿名策略。

        为什么要分登录/匿名两条路: `scene_mode_id` / `mode` 这两个参数对**匿名请求零过滤**
        (实测同一场景连采样 4 次歌单集合零交集, 跨场景交集率与不带场景的基线相同 —— 见文件头
        第十一/十二轮), 服务端只对登录态下发真正的「场景/偏好」个性化流。

        取数顺序:
          ① `POST /luna/pc/discover/mix`(block_type=discovery_playlist, 带 `scene_mode_id`
             或 `mode`) → `inner_block[].resources[].entity.playlist` = 该模式的官方歌单
             → `playlist/detail` 展开曲目(实测单歌单可达 121 首);
          ② 仍不足 `want` → 官方个性化推荐队列 `POST /luna/pc/feed/song-tab`(登录态下它是
             按**本账号听歌偏好**生成的)补足。
        失败(空/异常)一律返回 [], 由 `_feed_mode_tracks` 回落到「主题搜索 + 中文榜单」。
        """
        tracks, seen = [], set()
        body = {"block_type": "discovery_playlist", "sub_channel_id": 0,
                "exposure_radio_list": [], "cursor": "", "count": 20}
        sid = str(scene_id or "").strip()
        if sid:
            try:
                body["scene_mode_id"] = int(sid)
            except Exception:
                body["scene_mode_id"] = sid
        elif mode:
            body["mode"] = str(mode or "default")

        def add(objs):
            for item in (self._track(x) for x in (objs or [])):
                if not item or not item.get("id"):
                    continue
                tid = str(item["id"])
                if tid not in seen:
                    seen.add(tid)
                    tracks.append(item)

        for _round in range(3):
            if len(tracks) >= want:
                break
            try:
                data = self._req("/luna/pc/discover/mix", body)
            except Exception:
                data = {}
            blocks = data.get("inner_block") or []
            if not blocks:
                break
            ids = []
            for block in blocks:
                for res in (block.get("resources") or []):
                    entity = res.get("entity") if isinstance(res.get("entity"), dict) else {}
                    playlist = entity.get("playlist") if isinstance(entity.get("playlist"), dict) else {}
                    pid = str(playlist.get("id") or res.get("resource_id") or "")
                    if pid and pid not in ids:
                        ids.append(pid)
            for pid in ids[:4]:                         # 每轮最多展开 4 个歌单, 控时延
                if len(tracks) >= want:
                    break
                try:
                    add(self._playlist_tracks(pid))
                except Exception:
                    pass
            if len(tracks) >= want:
                break
            cursor = str(data.get("cursor") or data.get("next_cursor") or "")
            if not cursor or cursor == str(body.get("cursor") or ""):
                break
            body["cursor"] = cursor

        rounds = 0
        while len(tracks) < want and rounds < 4:
            rounds += 1
            try:
                data = self._req("/luna/pc/feed/song-tab", {
                    "played_media": [], "is_first_request": rounds == 1,
                    "is_did_first_request": rounds > 1,
                    "feed_counts": {"mix_session_count": rounds - 1}})
            except Exception:
                data = {}
            items = data.get("items") or []
            if not items:
                break
            add(items)

        return tracks[:want]

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
