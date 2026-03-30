# EDC Benchmark

一个最小可运行的 EDC benchmark 骨架，面向本科生批量执行实验。

## 当前已实现

- 统一仓库骨架

- `scripts/run_experiment.py` 单实验入口

- 统一输出四件套：
  - `config.yaml`
  - `metrics.csv`
  - `summary.json`
  - `run.log`
  
- 控制面性能测评
  •	Catalog Request
	•	Contract Offer Negotiation
	•	Contract Agreement
	•	Transfer Initiation
	
- 数据面性能评测
  •	小文件传输
	•	中等文件传输
	•	大文件传输
	•	并发传输
	
- 鲁棒性与异常场景评测
	•	provider connector 重启
	•	consumer connector 重启
	•	network delay
	
	•	packet-loss
	
	•	transfer-interruption

## 依赖
## 构建
```bash

./gradlew transfer:transfer-00-prerequisites:connector:build

run connectors：

provider：
java -Dedc.fs.config=transfer/transfer-00-prerequisites/resources/configuration/provider-configuration.properties -jar transfer/transfer-00-prerequisites/connector/build/libs/connector.jar

 java "-Dedc.fs.config=transfer/transfer-00-prerequisites/resources/configuration/provider-configuration.properties" -jar transfer/transfer-00-prerequisites/connector/build/libs/connector.jar
-------
consumer：
java -Dedc.fs.config=transfer/transfer-00-prerequisites/resources/configuration/consumer-configuration.properties -jar transfer/transfer-00-prerequisites/connector/build/libs/connector.jar

 java "-Dedc.fs.config=transfer/transfer-00-prerequisites/resources/configuration/consumer-configuration.properties" -jar transfer/transfer-00-prerequisites/connector/build/libs/connector.jar


```
## 启动 HTTP 服务器
```
docker build -t http-request-logger util/http-request-logger
docker run -p 4000:4000 http-request-logger
```


## 运行


```bash
1、合同协商
python -m scripts.run_experiment --config configs/negotiation_baseline.yaml
2、基本传输
python -m scripts.run_experiment --config configs/transfer_baseline.yaml
3、不同数据规模传输
python -m scripts.run_experiment --config configs/transfer_dataSize.yaml
4、并发传输
 python -m scripts.run_experiment --config configs/concurrent_transfer.yaml
5、provider中断鲁棒
python -m scripts.run_experiment --config configs/provider_restart_during_transfer.yaml
6、consumer中断鲁棒（transfer process 的状态存在 内存 store 里，consumer 重启后，transfer 状态上下文丢失了）
python -m scripts.run_experiment --config configs/consumer_restart_during_transfer.yaml 
7、网络延迟
 python -m scripts.run_experiment --config configs/network_delay_transfer.yaml
8、传输超时
 python -m scripts.run_experiment --config configs/transfer_interruption.yaml
 9、链路抖动
  python -m scripts.run_experiment --config configs/packet_loss_transfer.yaml
```


## 目录

```text
edc-benchmark/
  docker/
  configs/
  scenarios/
  scripts/
  metrics/
  results/
  docs/
  report_template/
```
## 生成不同文件大小

```
fsutil file createnew file_1mb.bin 1048576

fsutil file createnew file_10mb.bin 10485760

fsutil file createnew file_100mb.bin 104857600

然后在那个目录下启动 HTTP 服务：
python -m http.server 8088
```

## 加网络时延，Toxiproxy容器部署

```
docker run -d --name toxiproxy -p 8474:8474 -p 30001:30001 -p 30002:30002 ghcr.io/shopify/toxiproxy

docker ps
```

添加protocol代理在（docs目录下运行）：

```
curl.exe -X POST "http://localhost:8474/proxies" -H "Content-Type: application/json" --data-binary "@provider_protocol_proxy.json"
```

添加public代理：

```
curl.exe -X POST "http://localhost:8474/proxies" -H "Content-Type: application/json" --data-binary "@provider_public_proxy.json"
```

查看所有代理：

```
curl.exe "http://localhost:8474/proxies"
```

加protocol时延：

```
curl.exe -X POST "http://localhost:8474/proxies/provider_protocol_proxy/toxics" -H "Content-Type: application/json" --data-binary "@latency.json" 
```

加public超时：

```
curl.exe -X POST "http://localhost:8474/proxies/provider_public_proxy/toxics" -H "Content-Type: application/json" --data-binary "@timeout.json"
```


改latency(200,500,1000,2000)和flitter,timeout（10000，30000）同时 文件大小，中断注入时间也会影响

运行：

```
 python -m scripts.run_experiment --config configs/network_delay_transfer.yaml

 python -m scripts.run_experiment --config configs/transfer_interruption.yaml
```

 删除时延：

```
 curl.exe -X DELETE "http://localhost:8474/proxies/provider_protocol_proxy/toxics/latency"

  curl.exe -X DELETE "http://localhost:8474/proxies/provider_public_proxy/toxics/timeout"
```

验证是否加上时延或者删掉：

```
 curl.exe "http://localhost:8474/proxies/provider_protocol_proxy/toxics"

  curl.exe "http://localhost:8474/proxies/provider_public_proxy/toxics"
```

 主要看 catalog latency 和 contract-agreement-latency

 删除容器：

```
 docker rm -f toxiproxy
```



# 实验指南

## 1、实验一：基础场景测试‘

1. 执行构建命令、在不同终端run connector（如果第一条命令报错就用第二个）、启动HTTP服务器、生成不同文件大小启动Http服务

2. 修改配置文件

   打开negotiation_baseline.yaml,修改experiment_id和output_dir，后面加上自己的学号

   打开transfer_baseline.yaml，做同样的修改

   修改repeat次数（3、5、10、20）和asset_base_url（文件大小，直接改file_10mb或者file_100mb,或者其他大小的文件1、10、50、100、200)

3. 执行：

   合同协商：

   python -m scripts.run_experiment --config configs/negotiation_baseline.yaml

   基础传输：

   python -m scripts.run_experiment --config configs/transfer_baseline.yaml

## 2、实验二、不同文件大小和并发传输

1. 同实验一执行构建运行命令

2. 修改配置文件

   打开transfer_dataSize.yaml,修改experiment_id和output_dir，后面加上自己的学号

   修改repeat次数（3、5、10、20）和data_size_mb ,以及asset_base_url（文件大小，直接改file_10mb或者file_100mb,或者其他大小的文件1、10、50、100、200)，二者相对应，

   concurrent_transfer.yaml做同样的修改，并修改concurrency并行次数

3. 执行：

   不同数据规模传输
   python -m scripts.run_experiment --config configs/transfer_dataSize.yaml

   并发传输
    python -m scripts.run_experiment --config configs/concurrent_transfer.yaml

## 3、实验三、provider节点中断鲁棒测试

1. 执行构建命令

2. 建议先执行一次transfer_baseline测试是否正常运行

3. 打开provider_restart_during_transfer.yaml文件，修改experiment_id和output_dir，后面加上自己的学号，

4. 修改provider_restart_command和provider_restart_workdir，改成自己的文件路径

   修改repeat次数（3、5、10、20）

   修改data_size_mb ,以及asset_base_url（文件大小，直接改file_10mb或者file_100mb,或者其他大小的文件1、10、50、100、200)，二者相对应，

   修改fault_injection_delay_s（0.2、0.5、1、2、5）

   本实验的实验矩阵是对不同大小的文件在不同时间注入故障，测试成功率和延迟

5. 运行：

   provider中断鲁棒
   python -m scripts.run_experiment --config configs/provider_restart_during_transfer.yaml

## 4、实验四、consumer节点中断鲁棒

1. 步骤同实验三，

2. 执行：python -m scripts.run_experiment --config configs/consumer_restart_during_transfer.yaml 

3. 但结果一般会失败

   例如：

   ```
       {
         "run_index": 1,
         "error": "Transfer did not reach a terminal success state during observation window",
         "negotiation_state": "FINALIZED",
         "transfer_state": "UNKNOWN"
       },
   ```

   记录重要数据即可

## 5、实验五、网络时延测试

1. 构建，建议先执行一次transfer_baseline测试是否正常运行

2. 部署Toxiproxy容器，添加protocol代理，

3. 加protocol时延：打开docs文件夹，打开latency.json，添加不同latency和jitter, 参考数值见下表，建议单因素测试加全组合测试

4. 打开network_delay_transfer.yaml文件，修改experiment_id和output_dir，后面加上自己的学号，

5. 修改repeat次数（3、5、10、20）

   修改data_size_mb ,以及asset_base_url（文件大小，直接改file_10mb或者file_100mb,或者其他大小的文件1、10、50、100、200)，二者相对应，

6. 修改latency_ms，和你刚刚修改的latency对应

   本实验的实验矩阵是对不同大小的文件在不同网络延迟，测试成功率和延迟

7. 执行：

    python -m scripts.run_experiment --config configs/network_delay_transfer.yaml

## 6、实验六、传输超时测试

1. 构建，建议先执行一次transfer_baseline测试是否正常运行

2. 部署Toxiproxy容器，添加public代理，

3. 加public超时：打开docs文件夹，打开timeout.json，添加不同timeout

4. 打开transfer_interruption.yaml文件，修改experiment_id和output_dir，后面加上自己的学号，

5. 修改repeat次数（3、5、10、20）

   修改data_size_mb ,以及asset_base_url（文件大小，直接改file_10mb或者file_100mb,或者其他大小的文件1、10、50、100、200)，二者相对应，

6. 修改interruption_timeout_ms，和你刚刚修改的timeout对应,

7. 修改fault_injection_delay_s（0.2、0.5、1、2、5）、故障注入时间

   本实验的实验矩阵是对不同大小的文件在不同时间发生传输多久超时，测试成功率和延迟

8. 执行：

    python -m scripts.run_experiment --config configs/transfer_interruption.yaml

| 测试强度 | latency   | jitter   | timeout | 说明                            |
| -------- | --------- | -------- | ------- | ------------------------------- |
| 中度     | 200       | 50-100   | 3000    | 中等延迟+抖动                   |
| 高度     | 500-1000  | 200-500  | 5000    | 明显延迟+大抖动，测试系统鲁棒性 |
| 极端     | 1000-2000 | 500-1000 | 8000    | 模拟严重网络问题或长距离传输    |

## 7、实验七、链路抖动测试

1. 构建，建议先执行一次transfer_baseline测试是否正常运行

2. 部署Toxiproxy容器，添加protocol代理，添加public代理，

3. 打开packet_loss_transfer.yaml文件，修改experiment_id和output_dir，后面加上自己的学号，

4. 修改repeat次数（3、5、10、20）

   修改data_size_mb ,以及asset_base_url（文件大小，直接改file_10mb或者file_100mb,或者其他大小的文件1、10、50、100、200)，二者相对应，

5. 修改packet_slicer_average_size

   packet_slicer_size_variation

   packet_slicer_delay_u

   本实验的实验矩阵是对不同大小的文件在不同链路抖动的情况，测试成功率和延迟

6. 执行： python -m scripts.run_experiment --config configs/packet_loss_transfer.yaml

| 测试等级 | average_size | size_variation | delay_us | 说明                                 |
| -------- | ------------ | -------------- | -------- | ------------------------------------ |
| 轻度     | 1024         | 64             | 0        | 数据大块传输，抖动小                 |
| 中度     | 512          | 128            | 50       | 中等分片 + 小延迟                    |
| 重度     | 256          | 256            | 200      | 小分片 + 高抖动，网络不稳定          |
| 极端     | 128          | 512            | 500      | 非常碎 + 高延迟，模拟高丢包/网络抖动 |

**单因素测试**：先固定两个参数，只调整一个，观察对传输时间和失败率的影响。

**全组合测试**：结合不同级别参数，做压力矩阵。
