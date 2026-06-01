# Impala Query Profile Digest

Source file: `profile_summary.txt`

## SQL

```sql
WITH pl AS (SELECT * FROM (SELECT row_number() OVER (PARTITION
BY entity_id ORDER BY vu.event_ts ASC, vu.child_item_code ASC) rn, * FROM
analytics_demo.fact_item_events vu INNER JOIN
reference_demo.dim_item_catalog glos ON vu.child_item_code = glos.item_cd AND
glos.item_level = CAST(10 AS BIGINT) AND glos.item_type = CAST(1 AS BIGINT) AND
glos.is_active = CAST(1 AS BIGINT) WHERE vu.is_special_event = CAST(0 AS
TINYINT) AND dt >= '2013-01-01' AND dt <= '2013-12-31') t1 WHERE rn = CAST(1 AS
BIGINT)),br_pl AS (SELECT entity_id, group_item_code, item_code, event_ts,
dt, segment_id, start_date, end_date FROM (SELECT DISTINCT * FROM (SELECT
group_item_code, item_code, start_date, end_date, segment_id FROM
analytics_demo.dim_item_segments) t) br INNER JOIN pl ON
CAST(br.group_item_code AS BIGINT) = pl.child_item_code AND event_ts >=
CAST(br.start_date AS TIMESTAMP) AND event_ts <= CAST(br.end_date AS
TIMESTAMP)),unlock_hist AS (SELECT /* +straight_join */ vu.entity_id,
vu.parent_item_code, vu.child_item_code, max(vu.event_ts) event_ts FROM
analytics_demo.fact_item_events vu INNER JOIN pl ON vu.entity_id =
pl.entity_id AND vu.dt <= pl.dt AND vu.event_ts <= pl.event_ts WHERE
vu.is_special_event = CAST(0 AS TINYINT) GROUP BY vu.entity_id,
vu.parent_item_code, vu.child_item_code),repeated_items AS (SELECT
group_item_code, item_code, start_date, end_date, count(DISTINCT
segment_parent_item_code) n_parents FROM (SELECT group_item_code, item_code,
start_date, end_date, segment_id, item_rank, lead(item_code) OVER (PARTITION BY
segment_id, start_date, end_date ORDER BY item_rank ASC)
segment_parent_item_code FROM analytics_demo.dim_item_segments) t1 GROUP
BY group_item_code, item_code, start_date, end_date HAVING count(DISTINCT
segment_parent_item_code) > CAST(1 AS BIGINT)),res AS (SELECT
br_pl.entity_id, br_pl.group_item_code, br_pl.item_code,
vu.parent_item_code, CAST(vu.child_item_code AS BIGINT) child_item_code,
if(rv.item_code IS NOT NULL, CAST(1 AS TINYINT), CAST(0 AS TINYINT))
multi_parent_item, lead(vu.child_item_code) OVER (PARTITION BY
vu.entity_id, br_pl.group_item_code, segment_id ORDER BY glos.item_level DESC,
vu.event_ts DESC) next_item, vu.event_ts, glos.item_level
child_item_level, segment_id, if(nvl(bs.event_count, CAST(0 AS BIGINT)) = CAST(0
AS BIGINT), CAST(1 AS TINYINT), CAST(0 AS TINYINT)) is_skipped,
nvl(bs.event_count, CAST(0 AS BIGINT)) event_count, nvl(CAST(bs.duration_seconds
AS DOUBLE) / CAST(3600 AS DOUBLE), CAST(0 AS DOUBLE)) duration_hours FROM
br_pl INNER JOIN unlock_hist vu ON br_pl.entity_id = vu.entity_id AND
CAST(br_pl.item_code AS BIGINT) = vu.child_item_code AND vu.event_ts <=
br_pl.event_ts LEFT ANTI JOIN scratch_demo.excluded_items stg_un ON
br_pl.entity_id = stg_un.entity_id AND CAST(br_pl.item_code AS BIGINT)
= stg_un.item_code LEFT OUTER JOIN reference_demo.dim_item_catalog glos ON
glos.item_type = CAST(1 AS BIGINT) AND glos.item_cd = vu.child_item_code AND
glos.is_active = CAST(1 AS BIGINT) LEFT OUTER JOIN
analytics_demo.fact_item_transition_stats bs ON
br_pl.entity_id = bs.entity_id AND vu.parent_item_code = bs.parent_cd
AND vu.child_item_code = bs.child_cd AND vu.event_ts = bs.child_item_event_ts AND
bs.is_child_special_event = CAST(0 AS TINYINT) LEFT OUTER JOIN
repeated_items rv ON br_pl.group_item_code = rv.group_item_code AND
br_pl.item_code = rv.item_code AND br_pl.start_date = rv.start_date AND
br_pl.end_date = rv.end_date) SELECT entity_id, group_item_code, item_code,
parent_item_code, CAST(child_item_code AS STRING) child_item_code, event_ts,
child_item_level, segment_id, is_skipped, event_count, duration_hours FROM
(SELECT *, max(if(multi_parent_item = 1 AND next_item = parent_item_code,
1, 0)) OVER (PARTITION BY entity_id, group_item_code, segment_id)
is_target_multi_parent, max(if(multi_parent_item = 1, 1, 0)) OVER (PARTITION BY
entity_id, group_item_code, segment_id) segment_has_multiparent_item FROM res)
t1 WHERE (segment_has_multiparent_item = CAST(0 AS TINYINT) OR
(segment_has_multiparent_item = CAST(1 AS TINYINT) AND is_target_multi_parent =
CAST(1 AS TINYINT)))
```

## ExecSummary: important operator rows

```text
66:EXCHANGE                         1  125.128ms  125.128ms    5.96M       4.30K   16.65 MB        1.50 MB  UNPARTITIONED
F26:EXCHANGE SENDER                 1   10s627ms   10s627ms                        848.00 B              0
34:ANALYTIC                         1    9s082ms    9s082ms    6.37M      10.55K   24.52 MB       16.00 MB
33:SORT                             1    8s647ms    8s647ms    6.37M      10.55K    2.00 GB       48.00 MB
65:EXCHANGE                         1   99.680ms   99.680ms    6.37M      10.55K    9.27 MB        3.24 MB  HASH(entity_id,t.group_item_code,t.segment_id)
F25:EXCHANGE SENDER                 1    4s967ms    4s967ms                        848.00 B              0
32:ANALYTIC                         1    3s380ms    3s380ms    6.37M      10.55K   25.05 MB       16.00 MB
31:SORT                             1    9s969ms    9s969ms    6.37M      10.55K    1.95 GB       48.00 MB
64:EXCHANGE                         1  189.737ms  189.737ms    6.37M      10.55K    1.19 MB        3.17 MB  HASH(vu.entity_id,t.group_item_code,t.segment_id)
F24:EXCHANGE SENDER                 1    3s564ms    3s564ms                         2.95 KB              0
30:HASH JOIN                        1  541.959ms  541.959ms    6.37M      10.55K   46.14 MB        2.00 GB  LEFT OUTER JOIN, PARTITIONED
62:EXCHANGE                         1  151.250ms  151.250ms    6.37M      10.55K    1.12 MB        2.75 MB  HASH(t.group_item_code,t.item_code,t.end_date,t.start_date)
F19:EXCHANGE SENDER                 1    3s202ms    3s202ms                         2.95 KB              0
29:HASH JOIN                        1    6s936ms    6s936ms    6.37M      10.55K    4.84 GB        2.00 GB  LEFT OUTER JOIN, PARTITIONED
55:EXCHANGE                         1  144.661ms  144.661ms    6.37M      10.55K   11.44 MB        2.12 MB  HASH(entity_id,max(vu.event_ts),vu.child_item_code,vu.parent_item_code)
F16:EXCHANGE SENDER                 1    3s585ms    3s585ms                         3.20 KB              0
28:HASH JOIN                        1  368.373ms  368.373ms    6.37M      10.55K   17.01 MB       16.94 MB  LEFT OUTER JOIN, BROADCAST
27:HASH JOIN                        1    2s167ms    2s167ms    6.37M      10.55K  418.09 MB        2.00 GB  LEFT ANTI JOIN, PARTITIONED
52:EXCHANGE                         1  150.785ms  150.785ms    6.59M      10.55K    6.78 MB        1.76 MB  HASH(entity_id,t.item_code)
F14:EXCHANGE SENDER                 1    4s091ms    4s091ms                         3.06 KB              0
26:HASH JOIN                        1   21s538ms   21s538ms    6.59M      10.55K    5.38 GB        2.00 GB  INNER JOIN, PARTITIONED
50:EXCHANGE                         1  259.517ms  259.517ms   11.14M      10.55K   18.22 MB        1.31 MB  HASH(entity_id,t.item_code)
F06:EXCHANGE SENDER                 1    1s994ms    1s994ms                         3.07 KB              0
08:HASH JOIN                        1   52s385ms   52s385ms   11.14M      10.55K   46.06 MB        2.00 GB  INNER JOIN, PARTITIONED
41:EXCHANGE                         1   52.838ms   52.838ms    1.20M      10.55K   13.18 MB      957.18 KB  HASH(child_item_code)
F03:EXCHANGE SENDER                 1  530.747ms  530.747ms                         2.91 KB              0
06:ANALYTIC                         1    2s138ms    2s138ms    3.28M      10.55K   25.05 MB       16.00 MB
05:SORT                             1    2s160ms    2s160ms    3.28M      10.55K  288.02 MB       48.00 MB
38:EXCHANGE                         1   45.664ms   45.664ms    3.28M      10.55K   11.26 MB      866.79 KB  HASH(entity_id)
F02:EXCHANGE SENDER                 1  449.474ms  449.474ms                         3.23 KB              0
04:HASH JOIN                        1   25s980ms   25s980ms    3.28M      10.55K   17.32 GB        2.00 GB  INNER JOIN, PARTITIONED
36:EXCHANGE                         1   41.132us   41.132us      296      10.55K   24.00 KB      365.59 KB  HASH(glos.item_cd)
F00:EXCHANGE SENDER                 1  148.369us  148.369us                         3.88 KB              0
03:SCAN HDFS                        1  891.282ms  891.282ms      296      10.55K    2.63 MB       64.00 MB  reference_demo.dim_item_catalog glos
```

## Metric lines

```text
Operator                       #Hosts   Avg Time   Max Time    #Rows  Est. #Rows   Peak Mem  Est. Peak Mem  Detail
    - TotalBytesRead: 102.2 GiB (109690204718)
    - TotalBytesSent: 44.3 GiB (47569668941)
    - TotalTime: 2.7m (164578780532)
      - PeakMemoryUsage: 16.7 MiB (17494456)
      - RowsProduced: 5,959,302 (5959302)
      - TotalStorageWaitTime: 0ns (0)
      - TotalTime: 5.7m (340191795014)
        - ReadIoBytes: 0 B (0)
        - WriteIoBytes: 0 B (0)
        - PeakMemoryUsage: 16.0 KiB (16384)
        - TotalTime: 3.3m (196217288093)
        - PeakMemoryUsage: 16.7 MiB (17460131)
        - RowsReturned: 5,959,302 (5959302)
        - RowsReturnedRate: 41446 per second (41446)
        - TotalTime: 2.4m (143782242472)
          - ReadIoBytes: 0 B (0)
          - WriteIoBytes: 0 B (0)
        - PeakMemoryUsage: 381.5 KiB (390656)
        - TotalTime: 66ms (66786584)
        - PeakMemoryUsage: 16.7 MiB (17494456)
        - RowsProduced: 5,959,302 (5959302)
        - TotalStorageWaitTime: 0ns (0)
        - TotalTime: 5.7m (340191795014)
          - ReadIoBytes: 0 B (0)
          - WriteIoBytes: 0 B (0)
          - InactiveTotalTime: 2.9m (175871604548)
          - PeakMemoryUsage: 16.0 KiB (16384)
          - TotalTime: 3.3m (196217288093)
          - InactiveTotalTime: 2.4m (143657113667)
          - PeakMemoryUsage: 16.7 MiB (17460131)
          - RowsReturned: 5,959,302 (5959302)
          - RowsReturnedRate: 41446 per second (41446)
          - TotalTime: 2.4m (143782242472)
            - ReadIoBytes: 0 B (0)
            - WriteIoBytes: 0 B (0)
          - PeakMemoryUsage: 381.5 KiB (390656)
          - TotalTime: 66ms (66786584)
      - PeakMemoryUsage: 2.0 GiB (2164395020)
      - RowsProduced: 5,959,302 (5959302)
      - TotalStorageWaitTime: 0ns (0)
      - TotalTime: 5.6m (338787019929)
        - ReadIoBytes: 0 B (0)
        - WriteIoBytes: 0 B (0)
        - PeakMemoryUsage: 848 B (848)
        - SerializeBatchTime: 10.43s (10425925829)
        - TotalBytesSent: 674.0 MiB (706777394)
        - TotalTime: 3.1m (185992603058)
        - PeakMemoryUsage: 8.0 MiB (8404992)
        - RowsReturned: 5,959,302 (5959302)
        - RowsReturnedRate: 39054 per second (39054)
        - TotalTime: 2.5m (152590810566)
          - PeakMemoryUsage: 24.5 MiB (25714688)
          - RowsReturned: 6,367,612 (6367612)
          - RowsReturnedRate: 41783 per second (41783)
          - TotalTime: 2.5m (152395451385)
            - ReadIoBytes: 0 B (0)
            - WriteIoBytes: 0 B (0)
            - PeakMemoryUsage: 2.0 GiB (2147508224)
            - RowsReturned: 6,367,612 (6367612)
            - RowsReturnedRate: 44431 per second (44431)
            - TotalTime: 2.4m (143312514953)
              - ReadIoBytes: 0 B (0)
              - WriteIoBytes: 0 B (0)
              - PeakMemoryUsage: 9.3 MiB (9715712)
              - RowsReturned: 6,367,612 (6367612)
              - RowsReturnedRate: 47284 per second (47284)
              - TotalTime: 2.2m (134664679671)
                - ReadIoBytes: 0 B (0)
                - WriteIoBytes: 0 B (0)
        - PeakMemoryUsage: 968.0 KiB (991232)
        - TotalTime: 165ms (165213963)
        - PeakMemoryUsage: 2.0 GiB (2164395020)
        - RowsProduced: 5,959,302 (5959302)
        - TotalStorageWaitTime: 0ns (0)
        - TotalTime: 5.6m (338787019929)
          - ReadIoBytes: 0 B (0)
          - WriteIoBytes: 0 B (0)
          - InactiveTotalTime: 2.9m (175364955111)
          - PeakMemoryUsage: 848 B (848)
          - SerializeBatchTime: 10.43s (10425925829)
          - TotalBytesSent: 674.0 MiB (706777394)
          - TotalTime: 3.1m (185992603058)
          - PeakMemoryUsage: 8.0 MiB (8404992)
          - RowsReturned: 5,959,302 (5959302)
          - RowsReturnedRate: 39054 per second (39054)
          - TotalTime: 2.5m (152590810566)
            - PeakMemoryUsage: 24.5 MiB (25714688)
            - RowsReturned: 6,367,612 (6367612)
            - RowsReturnedRate: 41783 per second (41783)
            - TotalTime: 2.5m (152395451385)
              - ReadIoBytes: 0 B (0)
              - WriteIoBytes: 0 B (0)
              - PeakMemoryUsage: 2.0 GiB (2147508224)
              - RowsReturned: 6,367,612 (6367612)
              - RowsReturnedRate: 44431 per second (44431)
              - TotalTime: 2.4m (143312514953)
                - ReadIoBytes: 0 B (0)
                - WriteIoBytes: 0 B (0)
                - InactiveTotalTime: 2.2m (134564999010)
                - PeakMemoryUsage: 9.3 MiB (9715712)
                - RowsReturned: 6,367,612 (6367612)
                - RowsReturnedRate: 47284 per second (47284)
                - TotalTime: 2.2m (134664679671)
                  - ReadIoBytes: 0 B (0)
                  - WriteIoBytes: 0 B (0)
          - PeakMemoryUsage: 968.0 KiB (991232)
          - TotalTime: 165ms (165213963)
      - PeakMemoryUsage: 2.0 GiB (2106115023)
      - RowsProduced: 6,367,612 (6367612)
      - TotalStorageWaitTime: 0ns (0)
      - TotalTime: 2.3m (139475732793)
        - ReadIoBytes: 0 B (0)
        - WriteIoBytes: 0 B (0)
        - PeakMemoryUsage: 848 B (848)
        - SerializeBatchTime: 4.91s (4907422871)
        - TotalBytesSent: 877.4 MiB (920023813)
        - TotalTime: 4.98s (4978668240)
        - PeakMemoryUsage: 25.0 MiB (26263552)
        - RowsReturned: 6,367,612 (6367612)
        - RowsReturnedRate: 47476 per second (47476)
        - TotalTime: 2.2m (134119969679)
          - ReadIoBytes: 0 B (0)
          - WriteIoBytes: 0 B (0)
          - PeakMemoryUsage: 1.9 GiB (2088828928)
          - RowsReturned: 6,367,612 (6367612)
          - RowsReturnedRate: 48704 per second (48704)
          - TotalTime: 2.2m (130739558365)
            - ReadIoBytes: 0 B (0)
            - WriteIoBytes: 0 B (0)
            - PeakMemoryUsage: 1.2 MiB (1245184)
            - RowsReturned: 6,367,612 (6367612)
            - RowsReturnedRate: 52724 per second (52724)
            - TotalTime: 2.0m (120770401338)
    Estimated Per-Host Mem: 21690879634
Operator                       #Hosts   Avg Time   Max Time    #Rows  Est. #Rows   Peak Mem  Est. Peak Mem  Detail
          - BytesRead: 17.0 KiB (17439)
          - BytesReadDataNodeCache: 0 B (0)
          - BytesReadLocal: 17.0 KiB (17439)
          - BytesReadRemoteUnexpected: 0 B (0)
          - BytesReadShortCircuit: 17.0 KiB (17439)
          - PeakMemoryUsage: 244.7 KiB (250564)
          - RowBatchQueuePeakMemoryUsage: 49.0 KiB (50176)
          - RowsRead: 1,149 (1149)
          - RowsReturned: 1,149 (1149)
          - RowsReturnedRate: 778302 per second (778302)
          - ScannerThreadsTotalWallClockTime: 2ms (2754726)
          - TotalRawHdfsReadTime(*): 1ms (1458969)
          - TotalTime: 1ms (1476289)
            - ReadIoBytes: 0 B (0)
            - WriteIoBytes: 0 B (0)
        CodeGen
          - CodegenInvoluntaryContextSwitches: 0 (0)
          - CodegenTotalWallClockTime: 67ms (67368669)
            - CodegenSysTime: 989.00us (989000)
            - CodegenUserTime: 65ms (65682000)
          - CodegenVoluntaryContextSwitches: 51 (51)
          - PeakMemoryUsage: 268.5 KiB (274944)
          - TotalTime: 67ms (67376934)
        - PeakMemoryUsage: 346.7 KiB (355062)
        - RowsProduced: 1,500 (1500)
        - TotalStorageWaitTime: 1ms (1670256)
        - TotalTime: 379ms (379990623)
          - ReadIoBytes: 0 B (0)
          - WriteIoBytes: 0 B (0)
          - ExecTime: 312ms (312420709)
            - ExecTreeExecTime: 1ms (1079389)
          ExecOption: Hash Partitioned Sender Codegen Enabled
          - InactiveTotalTime: 310ms (310733088)
          - PeakMemoryUsage: 227.6 KiB (233104)
          - SerializeBatchTime: 263.84us (263836)
          - TotalBytesSent: 37.7 KiB (38651)
          - TotalTime: 311ms (311579848)
          ExecOption: PARQUET Codegen Enabled, Codegen enabled: 3 out of 3
          - BytesRead: 21.2 KiB (21731)
          - BytesReadDataNodeCache: 0 B (0)
          - BytesReadLocal: 21.2 KiB (21731)
          - BytesReadRemoteUnexpected: 0 B (0)
          - BytesReadShortCircuit: 21.2 KiB (21731)
          - PeakMemoryUsage: 226.8 KiB (232256)
          - RowBatchQueuePeakMemoryUsage: 49.0 KiB (50176)
          - RowsRead: 1,500 (1500)
          - RowsReturned: 1,500 (1500)
          - RowsReturnedRate: 1070899 per second (1070899)
          - ScannerThreadsTotalWallClockTime: 2ms (2494806)
          - TotalRawHdfsReadTime(*): 1ms (1016273)
          - TotalTime: 1ms (1400692)
            - ReadIoBytes: 0 B (0)
            - WriteIoBytes: 0 B (0)
        CodeGen
          - CodegenInvoluntaryContextSwitches: 0 (0)
          - CodegenTotalWallClockTime: 66ms (66716384)
            - CodegenSysTime: 983.00us (983000)
            - CodegenUserTime: 65ms (65163000)
          - CodegenVoluntaryContextSwitches: 38 (38)
          - PeakMemoryUsage: 268.5 KiB (274944)
          - TotalTime: 66ms (66725853)
        - PeakMemoryUsage: 426.5 KiB (436750)
        - RowsProduced: 1,619 (1619)
        - TotalStorageWaitTime: 2ms (2175093)
        - TotalTime: 379ms (379381523)
          - ReadIoBytes: 0 B (0)
          - WriteIoBytes: 0 B (0)
          - ExecTime: 310ms (310445256)
            - ExecTreeExecTime: 1ms (1133644)
          ExecOption: Hash Partitioned Sender Codegen Enabled
          - InactiveTotalTime: 308ms (308691087)
          - PeakMemoryUsage: 243.6 KiB (249488)
          - SerializeBatchTime: 278.07us (278070)
          - TotalBytesSent: 40.8 KiB (41749)
          - TotalTime: 309ms (309604248)
          ExecOption: PARQUET Codegen Enabled, Codegen enabled: 4 out of 4
          - BytesRead: 24.3 KiB (24878)
          - BytesReadDataNodeCache: 0 B (0)
          - BytesReadLocal: 24.3 KiB (24878)
          - BytesReadRemoteUnexpected: 0 B (0)
          - BytesReadShortCircuit: 24.3 KiB (24878)
          - PeakMemoryUsage: 341.4 KiB (349560)
          - RowBatchQueuePeakMemoryUsage: 89.0 KiB (91136)
          - RowsRead: 1,619 (1619)
          - RowsReturned: 1,619 (1619)
          - RowsReturnedRate: 1022517 per second (1022517)
          - ScannerThreadsTotalWallClockTime: 3ms (3651004)
          - TotalRawHdfsReadTime(*): 1ms (1519742)
          - TotalTime: 1ms (1583347)
            - ReadIoBytes: 0 B (0)
            - WriteIoBytes: 0 B (0)
        CodeGen
          - CodegenInvoluntaryContextSwitches: 1 (1)
          - CodegenTotalWallClockTime: 68ms (68012274)
            - CodegenSysTime: 986.00us (986000)
            - CodegenUserTime: 66ms (66185000)
          - CodegenVoluntaryContextSwitches: 39 (39)
          - PeakMemoryUsage: 268.5 KiB (274944)
          - TotalTime: 68ms (68020252)
        - PeakMemoryUsage: 440.3 KiB (450886)
        - RowsProduced: 1,220 (1220)
        - TotalStorageWaitTime: 3ms (3018978)
        - TotalTime: 379ms (379072689)
          - ReadIoBytes: 0 B (0)
          - WriteIoBytes: 0 B (0)
          - ExecTime: 306ms (306814210)
            - ExecTreeExecTime: 1ms (1424045)
          ExecOption: Hash Partitioned Sender Codegen Enabled
          - InactiveTotalTime: 304ms (304741693)
          - PeakMemoryUsage: 203.6 KiB (208528)
          - SerializeBatchTime: 241.39us (241392)
          - TotalBytesSent: 31.2 KiB (31949)
          - TotalTime: 305ms (305488396)
          ExecOption: PARQUET Codegen Enabled, Codegen enabled: 4 out of 4
```

## Query Doctor instructions

Use only evidence from this digest.

Do not recommend disabling codegen unless CodegenTotalWallClockTime / CodegenTime is explicitly one of the dominant timings.

Do not recommend HDFS block-size or replication changes unless the digest clearly shows small files / many scan ranges / storage wait as the dominant bottleneck.

Prioritize:
1. Cardinality estimate errors: actual rows vs estimated rows.
2. SORT / ANALYTIC / JOIN / AGGREGATION operators by time and memory.
3. Network exchange / bytes sent.
4. Scan volume and partition pruning.
5. Spill / memory pressure.
6. Admission / planning / metadata only if visible in the digest.
