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

## 依赖
## 构建
```bash

./gradlew transfer:transfer-00-prerequisites:connector:build

run connectors
java -Dedc.fs.config=transfer/transfer-00-prerequisites/resources/configuration/provider-configuration.properties -jar transfer/transfer-00-prerequisites/connector/build/libs/connector.jar

 java "-Dedc.fs.config=transfer/transfer-00-prerequisites/resources/configuration/provider-configuration.properties" -jar transfer/transfer-00-prerequisites/connector/build/libs/connector.jar
-------
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
4、不同政策复杂度
python -m scripts.run_experiment --config configs/policy_overhead.yaml
5、provider中断鲁棒
python -m scripts.run_experiment --config configs/provider_restart_during_transfer.yaml
6、consumer中断鲁棒（transfer process 的状态存在 内存 store 里，consumer 重启后，transfer 状态上下文丢失了）
python -m scripts.run_experiment --config configs/consumer_restart_during_transfer.yaml 
7、网络延迟
 python -m scripts.run_experiment --config configs/network_delay_transfer.yaml
8、传输超时
 python -m scripts.run_experiment --config configs/transfer_interruption.yaml
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

加public时延：

```
curl.exe -X POST "http://localhost:8474/proxies/provider_public_proxy/toxics" -H "Content-Type: application/json" --data-binary "@timeout.json"
```


改latency(200,500,1000,2000)和flitter,同时 文件大小，中断注入时间也会影响

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

