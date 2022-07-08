import csv
import os
import glob
from prettytable import PrettyTable #needs pip3 install
from operator import itemgetter
import threading
import time
import sys
import requests #needs pip3 install
import influxdb_client
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import argparse

# Helper function to find the index of value of some known key from the baseline data query
def get_index(a):
	if a == 'Objects':
		return 0
	if a == 'ShallowHeap':
		return 1
	if a == 'RetainedHeap':
		return 2
	if a == 'PercentageRetainedHeap':
		return 3
	#If string does not match any of the 4 strings above, then raise an Error
	raise ValueError("Wrong field name present: " + a)

#Function to load baseline from file taken from input and store in a dict
def load_baseline(measurement_name):
	baseline = {}
	# Querying data with influx to get mean of previous n days (customizable)
	print("Getting baseline from influx")
	query = """from(bucket: "%s")
	|> range(start: -%s)
	|> filter(fn: (r) => r._measurement == "%s")
	|> mean()
	""" % (args.server_name, args.baselineDuration, measurement_name)
	#Initializing influxDB variables for query
	token = args.influx_token
	org = args.influx_org_name
	url = args.influx_url
	client = influxdb_client.InfluxDBClient(url = url, token = token, org = org)
	query_api = client.query_api()
	tables = query_api.query(query, org = org)
	print("Printing query results: ")
	for table in tables:
		for record in table:
			if record['ClassName'] not in baseline:
				baseline[record['ClassName']]=[0,0,0,0]
			baseline[record['ClassName']][get_index(record['_field'])]=record['_value']
	print("{" + "\n".join("{!r}: {!r},".format(k, v) for k, v in baseline.items()) + "}")
	print("-*"*100)
	return baseline

# Worker thread function to execute dominator tree and histogram for the given hprof file
def Dom_api(heap_filename, all_data, histo_data):
	print('Running dominator_tree command using MAT api.')
	os.system('java -Xmx'+ args.maxHeap + ' -jar ' + args.mat_path + '/mat/plugins/org.eclipse.equinox.launcher_*.jar -consolelog -application org.eclipse.mat.api.parse '+heap_filename+' -command="dominator_tree -groupBy BY_CLASS" -format=csv -unzip org.eclipse.mat.api:query')
	print('dominator_tree command complete')
	csv_folder = heap_filename[:-6] + '_Query/pages'
	filenames = glob.glob(csv_folder + '/*.csv')
	# Initialized total_retained_heap as -1
	# Will calculate it from the result of dominator tree
	# Will be used to get percentage retained heap for histogram data
	total_retained_heap = -1
	for file in filenames:
		with open(file, 'r') as f:
			csvr = csv.reader(f)
			header = next(csvr)
			for row in csvr:
				row[4]=float(row[4])*100
				if(total_retained_heap < 0):
					total_retained_heap = (int(row[3])/row[4]) * 100
				if args.excludeSystemClass and (row[0].startswith('java') or row[0].startswith('jdk')):
					continue
				all_data.append(row)
	print("\nLength: ", len(all_data))
	# If total_retained_heap is still negative or zero,
	# some error has occured during Eclipse MAT command.
	# The error would be printed in logs
	# Skip histogram command and exit program (TODO: send error to slack)
	if(total_retained_heap <= 0):
		return
	# Running system_overview report to get class histrogram with retained heap sizes
	print("Trying histogram, to check if the retained size is present or not")
	os.system('java -Xmx' + args.maxHeap + ' -jar ' + args.mat_path + '/mat/plugins/org.eclipse.equinox.launcher_*.jar -consolelog -application org.eclipse.mat.api.parse '+heap_filename+' -format=csv -unzip org.eclipse.mat.api:overview')
	print("Finished overview command!!")
	csv_folder = heap_filename[:-6] + '_System_Overview/pages'
	filenames = glob.glob(csv_folder + '/Class_Histogram*.csv')
	for file in filenames:
		with open(file, 'r') as f:
			csvr = csv.reader(f)
			header = next(csvr)
			for row in csvr:
				if args.excludeSystemClass and (row[0].startswith('java') or row[0].startswith('jdk')):
					continue
				if(len(row) == 5):
					row[4] = ((100.0 * int(row[3]))/ total_retained_heap)
				elif(len(row) == 4):
					row.append(((100.0 * int(row[3]))/ total_retained_heap))
				else:
					row = row[:4].append(((100.0 * int(row[3]))/ total_retained_heap))
				histo_data.append(row)
	print("\nHisto data: ", histo_data)
	print("\nLength of Histo Data: ", len(histo_data))

# Function to write data to influxDB
def influx_push(all_data, histo_data):
	print("Starting influx thread to post data")
	# Setting up basic variables for influxDB
	token = args.influx_token
	org = args.influx_org_name
	url = args.influx_url

	client = influxdb_client.InfluxDBClient(url = url, token = token, org = org)
	bucket = args.server_name
	write_api = client.write_api(write_options = SYNCHRONOUS)
	total_sent = 0
	for row in all_data:
		print("SENDING POINT: ", row, " INDEX: ", total_sent)
		total_sent += 1
		# Don't send data points which have less than 0.005% of retained heap size
		if(round(float(row[4]), 2) != 0.0):
			point = (Point(args.dominator_tree_measurement).tag("ClassName", row[0]).field("PercentageRetainedHeap", float(row[4])).field("Objects", int(row[1])).field("ShallowHeap", int(row[2])).field("RetainedHeap", int(row[3])))
			write_api.write(bucket = bucket, org=org, record = point)
	print('Sent the dominator_tree data to influx')
	print('-*-'*60)
	print('*-*'*60)
	print('Sending the histo data to influx')
	# Posting histo data to influx
	# No need to have a minimum value of any field to push, since it only has top 25 entries
	total_sent = 0
	for row in histo_data:
		print("SENDING POINT: ", row, " INDEX: ", total_sent)
		total_sent += 1
		point = (Point(args.histogram_measurement).tag("ClassName", row[0]).field("PercentageRetainedHeap", float(row[4])).field("Objects", int(row[1])).field("ShallowHeap", int(row[2])).field("RetainedHeap", int(row[3])))
		write_api.write(bucket = bucket, org=org, record = point)
	print("Finished posting all data")

#FORMAT OF DOMINATOR CSV OUTPUT:
#Class Name,Objects,Shallow Heap,Retained Heap,Percentage,
# COMMAND: docker run -d --name test2 --mount type=bind,source="$(pwd)",target=/dump b:1 /multi.py (0) /opt (1) /dump/Main.hprof (2) Run with or without baseline, 0 for without, anything else for with baseline (3) <ServerName> (4) <INFLUX org name> (5) <Slack_Incoming_Webhook> (6) <INFLUX token> (7) <Dominator_tree Bucket name> (8) <Histogram Bucket name> (9) <INFLUX URL> (10) Whether to exclude system classes or not (0 or 1) (11) <Maximum heap size for MAT> (12) <How many previous days for baseline retrieval> (13)
if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='HeapDump comparison and anomaly detection')
	parser.add_argument('mat_path', help = 'Path where Eclipse MAT is installed. When run inside docker it is /opt')
	parser.add_argument('heap_filename', help = 'Heap dump file path')
	parser.add_argument('server_name', help = 'Server name')
	parser.add_argument('influx_org_name', help = 'Influx org name')
	parser.add_argument('slack_incoming_webhook', help = 'Slack incoming webhook')
	parser.add_argument('influx_token', help = 'InfluxDB token')
	parser.add_argument('dominator_tree_measurement', help = 'Dominator tree measurement name for influxDB')
	parser.add_argument('histogram_measurement', help = 'Histogram data measurement name for influxDB')
	parser.add_argument('influx_url', help = 'InfluxDB URL')
	parser.add_argument('--getBaseline', help = 'Whether to load baseline data from influx or not', action='store_true')
	parser.add_argument('--excludeSystemClass', help = 'Whether to exclude system classes or not', action = 'store_true')
	parser.add_argument('--maxHeap', help = 'Maximum heap size for MAT', default = '4g')
	parser.add_argument('--baselineDuration', help = 'Duration to get baseline data from influx', default='14d')
	global args
	args = parser.parse_args()
	# if(len(sys.argv)!=14):
	# 	print("WRONG FORMAT OF ARGUMENTS: ", sys.argv, len(sys.argv))
	# 	os._exit(-1)
	print("Arguments: ", sys.argv)
	t = time.process_time()
	t1 = time.time()
	heap_filename = args.heap_filename
	heap_filename.strip()
	# Check if the heap dump file is in hprof format
	if(heap_filename[-6:] != '.hprof'):
		print('You enterred: ' + heap_filename + '. Last characters are: ' + heap_filename[-6:])
		print('Heap File name should end in ".hprof"')
		os._exit(-1)
	print("Correct heap file name: ", heap_filename)
	all_data = []
	histo_data = []
	#Call Thread to run dominator_tree api
	dom_thread = threading.Thread(target = Dom_api, name = 'dom_thread', args = (heap_filename, all_data,histo_data,))
	dom_thread.start()
	baseline = {}
	# Don't load baseline if specified by user
	if(args.getBaseline):
		baseline = load_baseline(args.dominator_tree_measurement)
	histo_baseline = {}
	# Don't load baseline if specified by user
	if(args.getBaseline):
		histo_baseline = load_baseline(args.histogram_measurement)
	# Print tablular output
	table = PrettyTable(['ClassName', 'Objects', 'Objects(S-B)', 'Shallow Heap', 'Shallow Heap(S-B)', 'Retained Heap', 'Retained Heap(S-B)', 'Percentage', 'Percentage(S-B)'])
	anomaly_table = PrettyTable(['ClassName', 'RetainedHeap(RH)', 'RH-Diff', '%Diff'])
	histo_table = PrettyTable(['ClassName', 'Objects', 'Objects(S-B)', 'Shallow Heap', 'Shallow Heap(S-B)', 'Retained Heap', 'Retained Heap(S-B)', 'Percentage', 'Percentage(S-B)'])
	histo_anomaly_table = PrettyTable(['ClassName', 'RetainedHeap(RH)', 'RH-Diff', '%Diff'])
	threshold_deviation_percent = 5
	threshold_deviation_heap = 1024*1024*100
	threshold_deviation_retained_heap = 1024*1024*500
	total_anomalies = 0
	anomaly_array = []
	total_histo_anomalies = 0
	# Wait for dom_thread to finish
	print("Waiting to join thread")
	dom_thread.join()
	print("\nThread OVER: ", len(all_data))
	# If no data is loaded from dominator tree or histogram, don't proceed
	if(len(all_data) == 0 and len(histo_data) == 0):
		response = requests.post(slack_incoming_webhook, data='{"text":"Some error occured during parsing of heap dump. Please check logs file. Both DOMINATOR TREE and Histogram are empty"}', headers={'Content-type': 'application/json'})
		os._exit(-1)
	#INFLUX integration for writing data
	influx_thread = threading.Thread(target = influx_push, name = 'influx_push_thread', args = (all_data,histo_data,))
	influx_thread.start()
	# Comparing data from baseline and given hprof file and printing in form of table
	for row in all_data:
		className,objects,shallow_heap,retained_heap,percentage = row[:5]
		objects = int(objects)
		shallow_heap = int(shallow_heap)
		retained_heap = int(retained_heap)
		baseline_row = list(map(float, baseline.get(className, [0,0,0,0.0])))
		new_row = [className, objects, int(objects - baseline_row[0]), shallow_heap, int(shallow_heap - baseline_row[1]), retained_heap, int(retained_heap - baseline_row[2]), round(percentage, 3), round(percentage - baseline_row[3], 3)]
		table.add_row(new_row)
		if((new_row[6]>=threshold_deviation_heap and new_row[8]>=threshold_deviation_percent) or new_row[6]>=threshold_deviation_retained_heap):
			anomaly_table.add_row([className, new_row[5], new_row[6], new_row[8]])
			anomaly_array.append([className, new_row[8]])
			total_anomalies += 1
	for row in histo_data:
		className,objects,shallow_heap,retained_heap,percentage = row[:5]
		objects = int(objects)
		shallow_heap = int(shallow_heap)
		retained_heap = int(retained_heap)
		baseline_row = list(map(float, histo_baseline.get(className, [0,0,0,0.0])))
		new_row = [className, objects, int(objects - baseline_row[0]), shallow_heap, int(shallow_heap - baseline_row[1]), retained_heap, int(retained_heap - baseline_row[2]), round(percentage, 3), round(percentage - baseline_row[3], 3)]
		histo_table.add_row(new_row)
		if((new_row[6]>=threshold_deviation_heap and new_row[8]>=threshold_deviation_percent) or new_row[6]>=threshold_deviation_retained_heap):
			histo_anomaly_table.add_row([className, new_row[5], new_row[6], new_row[8]])
			total_histo_anomalies += 1
	print("-"*100)
	print('Total Anomalies in COMPARED DOMINATOR TREE: ', total_anomalies)
	print(anomaly_table.get_string(sortby='RetainedHeap(RH)', reversesort=True))
	# Store the incoming web-hook in URL
	URL = args.slack_incoming_webhook
	slack_data = '{"text": "```\nServer Name: ' + args.server_name + '\nTotal Anomalies in COMPARED DOMINATOR TREE: ' + str(total_anomalies) + '\n' + anomaly_table.get_string(sortby='RetainedHeap(RH)', reversesort=True) + '\n```"}'
	if total_anomalies == 0:
		print("No Anomalies Found in COMPARED DOMINATOR TREE!!")
		# If no anomalies, change the text to state no anomalies present
		slack_data = '{"text": "Server Name: ' + args.server_name + '\n*HOORAY!! NO ANOMALIES FOUND IN COMPARED DOMINATOR TREE*"}'
	print(slack_data)
	response = requests.post(URL, data=slack_data, headers={'Content-type': 'application/json'})
	if(response.status_code != 200):
		raise ValueError('Request to slack returned an error %s, the response is:\n%s'% (response.status_code, response.text))
	print("-"*100)
	print("DOMINATOR TREE COMPARISON TABLE: ")
	# Print compared dominator tree table in logs
	print(table.get_string(sort_key=itemgetter(8,9), sortby='Percentage', reversesort=True))
	print('-'*100)
	print('-'*100)
	print('-'*100)
	print("Histogram data")
	# Print compared histogram table in logs
	print(histo_table.get_string(sort_key=itemgetter(8,9), sortby='Percentage', reversesort=True))
	slack_data = '{"text": "```\nServer Name: ' + args.server_name + '\nTotal Anomalies in Histogram data: ' + str(total_histo_anomalies) + '\n' + histo_anomaly_table.get_string(sortby='RetainedHeap(RH)', reversesort=True) + '\n```"}'
	if(total_histo_anomalies == 0):
		print("NO ANOMALIES FOUND in Histogram data")
		# If no anomalies, change the text to state no anomalies present
		slack_data = '{"text": "Server Name: ' +args.server_name + '\n*HOORAY!! NO ANOMALIES FOUND IN Histogram data*"}'
	response = requests.post(URL, data=slack_data, headers={'Content-type': 'application/json'})
	if(response.status_code != 200):
		raise ValueError('Request to slack returned an error %s, the response is:\n%s'% (response.status_code, response.text))
	print('Finished sending to slack')
	# Wait for influx thread to join
	influx_thread.join()
	print('*'*100)
	print('*'*100)
	print('Elapsed CPU time: ', time.process_time() - t)
	print('Elapsed total time: ', time.time() - t1)



