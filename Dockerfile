FROM eclipse-temurin:18-alpine
RUN wget -q "https://download.eclipse.org/mat/snapshots/rcp_1.13/org.eclipse.mat.ui.rcp.MemoryAnalyzer-linux.gtk.x86_64.zip" -O /tmp/org.eclipse.mat.ui.rcp.MemoryAnalyzer-linux.gtk.x86_64.zip
RUN unzip /tmp/org.eclipse.mat.ui.rcp.MemoryAnalyzer-linux.gtk.x86_64.zip -d /opt 
RUN chmod +x /opt/mat/MemoryAnalyzer /opt/mat/ParseHeapDump.sh
ENV PYTHONUNBUFFERED=1
RUN apk add --update --no-cache python3 && ln -sf python3 /usr/bin/python
RUN python3 -m ensurepip
RUN pip3 install prettytable
RUN pip3 install requests
RUN pip3 install influxdb-client
ENTRYPOINT ["python3"]
