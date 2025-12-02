import { createChart, ColorType, CandlestickSeries, AreaSeries } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, UTCTimestamp, LogicalRange } from 'lightweight-charts';
import { useEffect, useRef, useCallback, useState } from 'react';
import api from '../api/client';

interface CandleData {
  ticker_id: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface ChartProps {
  tickerId: string;
  interval?: '1m' | '1d';
  chartType?: 'candle' | 'area';
}

export const CandleChart = ({ tickerId, interval = '1m', chartType = 'candle' }: ChartProps) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick" | "Area"> | null>(null);
  
  // State refs to avoid re-renders disrupting chart
  const isFetchingHistory = useRef(false);
  const earliestTimestamp = useRef<string | null>(null);
  const allDataRef = useRef<any[]>([]);
  const hasMoreHistory = useRef(true); // New: Stop fetching if no more data
  
  const [status, setStatus] = useState<'loading' | 'ready' | 'empty' | 'error'>('loading');

  // Transform API data to Chart data
  const transformData = useCallback((data: CandleData[]) => {
    return data.map(c => {
      const base = { time: (new Date(c.timestamp).getTime() / 1000) as UTCTimestamp };
      if (chartType === 'area') {
          return { ...base, value: c.close };
      }
      return {
        ...base,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      };
    }).sort((a, b) => (a.time as number) - (b.time as number));
  }, [chartType]);

  // Load Initial Data
  const loadInitialData = useCallback(async () => {
    if (!seriesRef.current) return;

    setStatus('loading');
    hasMoreHistory.current = true;
    
    try {
      console.log("[CandleChart] Loading initial data for:", tickerId);
      const data = await api.get(`market/candles/${tickerId}`, {
        searchParams: { interval, limit: 300 }
      }).json<CandleData[]>();

      if (data.length > 0) {
        const formatted = transformData(data);
        const unique = formatted.filter((v, i, a) => a.findIndex(t => t.time === v.time) === i);
        
        seriesRef.current.setData(unique);
        allDataRef.current = unique;
        // Backend returns [Oldest, ..., Newest]
        earliestTimestamp.current = data[0].timestamp;

        if (chartRef.current) {
            chartRef.current.timeScale().fitContent();
        }
        setStatus('ready');
      } else {
        console.warn("[CandleChart] No data found.");
        setStatus('empty');
        hasMoreHistory.current = false;
      }
    } catch (err) {
      console.error("[CandleChart] Failed to load initial data", err);
      setStatus('error');
    }
  }, [tickerId, interval, transformData]);

  // Load Historical Data
  const loadMoreHistory = useCallback(async () => {
    if (isFetchingHistory.current) return;
    if (!hasMoreHistory.current) return; // Don't fetch if known empty
    if (!earliestTimestamp.current) return;
    if (!seriesRef.current) return;

    isFetchingHistory.current = true;
    // console.log("[CandleChart] Fetching history before:", earliestTimestamp.current);
    
    try {
      const data = await api.get(`market/candles/${tickerId}`, {
        searchParams: { 
            interval, 
            limit: 300,
            before: earliestTimestamp.current
        }
      }).json<CandleData[]>();

      if (data.length > 0) {
        // console.log(`[CandleChart] Received ${data.length} historical candles.`);
        const formatted = transformData(data);
        
        // Filter duplicates
        const uniqueNew = formatted.filter(n => !allDataRef.current.some(e => e.time === n.time));
        
        if (uniqueNew.length > 0) {
            const merged = [...uniqueNew, ...allDataRef.current];
            seriesRef.current.setData(merged);
            allDataRef.current = merged;
            earliestTimestamp.current = data[0].timestamp;
            // console.log("[CandleChart] History updated. New oldest:", earliestTimestamp.current);
        } else {
             // console.log("[CandleChart] No new unique candles found in history batch.");
             // If backend returns data but all are duplicates, it likely means we hit the end or a loop
             // But typically backend 'before' logic prevents this.
             // Safe to assume end of history for now or retry logic.
             // hasMoreHistory.current = false; 
        }
        
        if (data.length < 300) {
            // Less than limit returned means end of history
            hasMoreHistory.current = false;
            console.log("[CandleChart] End of history reached (count < limit).");
        }

      } else {
          console.log("[CandleChart] No more history available (empty list).");
          hasMoreHistory.current = false;
      }
    } catch (err) {
      console.error("[CandleChart] Failed to load history", err);
    } finally {
      isFetchingHistory.current = false;
    }
  }, [tickerId, interval, transformData]);

  // Real-time Update (Polling)
  useEffect(() => {
    const poll = setInterval(async () => {
      if (!seriesRef.current) return;
      try {
          const data = await api.get(`market/candles/${tickerId}`, {
            searchParams: { interval, limit: 5 }
          }).json<CandleData[]>();
          
          if (data.length > 0) {
              const formatted = transformData(data);
              formatted.forEach(bar => {
                  seriesRef.current?.update(bar);
              });
              // Ideally we should also update allDataRef to keep it in sync for deduplication
              // but for history fetching 'before' logic, it usually works on the tail.
          }
      } catch (e) {
          // silent fail
      }
    }, 2000);

    return () => clearInterval(poll);
  }, [tickerId, interval, transformData]);

  // Initialize Chart & Event Listeners
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#101623' },
        textColor: '#90a4cb',
      },
      grid: {
        vertLines: { color: '#1f2937' },
        horzLines: { color: '#1f2937' },
      },
      width: chartContainerRef.current.clientWidth,
      height: chartContainerRef.current.clientHeight,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: '#314368',
      },
      rightPriceScale: {
        borderColor: '#314368',
      },
      // Enable Mouse Wheel Zoom, Disable Wheel Scroll
      handleScale: {
        mouseWheel: true,
      },
      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
      kineticScroll: {
        touch: false,
        mouse: false,
      },
    });

    let series: ISeriesApi<"Candlestick" | "Area">;

    if (chartType === 'area') {
        series = chart.addSeries(AreaSeries, {
            topColor: 'rgba(13, 89, 242, 0.4)', // Brand Primary with opacity
            bottomColor: 'rgba(13, 89, 242, 0)',
            lineColor: '#0d59f2',
            lineWidth: 2,
        });
    } else {
        series = chart.addSeries(CandlestickSeries, {
            upColor: '#00FF41',
            downColor: '#ef4444',
            borderVisible: false,
            wickUpColor: '#00FF41',
            wickDownColor: '#ef4444',
        });
    }

    chartRef.current = chart;
    seriesRef.current = series;

    loadInitialData();

    const handleVisibleLogicalRangeChange = (range: LogicalRange | null) => {
        if (range) {
            // When scrolling to the left (past 0 logical index), load more
            if (range.from < 50) { 
                loadMoreHistory();
            }
        }
    };
    
    chart.timeScale().subscribeVisibleLogicalRangeChange(handleVisibleLogicalRangeChange);

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ 
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight 
        });
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(handleVisibleLogicalRangeChange);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [loadInitialData, loadMoreHistory, chartType]);

  return (
    <div className="w-full h-full relative group">
      <div ref={chartContainerRef} className="w-full h-full" />
      
      {/* Status Overlay */}
      {status !== 'ready' && (
        <div className="absolute inset-0 flex items-center justify-center bg-[#101623]/80 z-10 pointer-events-none">
            {status === 'loading' && <span className="text-[#90a4cb] animate-pulse">Loading Chart...</span>}
            {status === 'empty' && <span className="text-[#90a4cb]">No Data Available</span>}
            {status === 'error' && <span className="text-red-500">Failed to Load Chart</span>}
        </div>
      )}
    </div>
  );
};
