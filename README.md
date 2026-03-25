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


## 依赖
## 构建
```bash

./gradlew transfer:transfer-00-prerequisites:connector:build

run connectors
java -Dedc.fs.config=transfer/transfer-00-prerequisites/resources/configuration/provider-configuration.properties -jar transfer/transfer-00-prerequisites/connector/build/libs/connector.jar

java -Dedc.fs.config=transfer/transfer-00-prerequisites/resources/configuration/consumer-configuration.properties -jar transfer/transfer-00-prerequisites/connector/build/libs/connector.jar


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
python -m scripts.run_experiment --config configs/policy_overhead_simple.yaml

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

