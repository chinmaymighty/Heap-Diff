# Heap-Diff
Script to compare heap dumps and detect anomalies of increase in memory usage
Docker run command:
```
usage: multi.py [-h] [--getBaseline] [--excludeSystemClass] [--maxHeap MAXHEAP] [--baselineDuration BASELINEDURATION]
                mat_path heap_filename server_name influx_org_name slack_incoming_webhook influx_token dominator_tree_measurement
                histogram_measurement influx_url

HeapDump comparison and anomaly detection

positional arguments:
  mat_path              Path where Eclipse MAT is installed. When run inside docker it is /opt
  heap_filename         Heap dump file path
  server_name           Server name
  influx_org_name       Influx org name
  slack_incoming_webhook
                        Slack incoming webhook
  influx_token          InfluxDB token
  dominator_tree_measurement
                        Dominator tree measurement name for influxDB
  histogram_measurement
                        Histogram data measurement name for influxDB
  influx_url            InfluxDB URL

optional arguments:
  -h, --help            show this help message and exit
  --getBaseline         Whether to load baseline data from influx or not
  --excludeSystemClass  Whether to exclude system classes or not
  --maxHeap MAXHEAP     Maximum heap size for MAT
  --baselineDuration BASELINEDURATION
                        Duration to get baseline data from influx
```
To run inside docker:
```
docker run -d --name <ContainerName> --mount type=bind,src=<Path where python script and hprof file is present>,target=/dump <Docker_Image_ID> /dump/multip.py <List of arguments to follow are described above>
```
Link to presentation:
https://docs.google.com/presentation/d/1_7MoDe0IIEwQfAThMAGQd5DMVpAxhWyrgQbzjRiuMec/edit?usp=sharing
