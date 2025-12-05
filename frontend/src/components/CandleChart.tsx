import { createChart, ColorType, CandlestickSeries, AreaSeries } from 'lightweight-charts';
import type { IChartApi, ISeriesApi, UTCTimestamp, LogicalRange } from 'lightweight-charts';
import { useEffect, useRef, useCallback, useState } from 'react';
import api from '../api/client';
import { getCurrencyDigits, formatCurrencyDisplay } from '../utils/numfmt';
import { usePrice } from '../store/prices';
import Skeleton from './Skeleton';

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
  range?: '1D' | '1W' | '3M' | '1Y' | '5Y';
  chartType?: 'candle' | 'area';
  lastPrice?: number;
  lastPriceTimestamp?: number; // In milliseconds
  currencyCode?: string;
}

export const CandleChart = ({ tickerId, range = '1D', chartType = 'candle', lastPrice, lastPriceTimestamp, currencyCode }: ChartProps) => {
    // Prefer external lastPrice if provided, otherwise subscribe to store
    const storePrice = usePrice(tickerId);
    const rtPrice = (typeof lastPrice === 'number') ? lastPrice : (typeof storePrice === 'number' ? storePrice : undefined);
    const rtTimestamp = lastPriceTimestamp;
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick" | "Area"> | null>(null);
  
  // Map range to interval
  // 1D and 1W use 1m interval for detail. 3M+ use 1d.
  const interval = (range === '1D' || range === '1W') ? '1m' : '1d';

  // State refs to avoid re-renders disrupting chart
  const isFetchingHistory = useRef(false);
  const earliestTimestamp = useRef<string | null>(null);
  const allDataRef = useRef<any[]>([]);
  const hasMoreHistory = useRef(true); // New: Stop fetching if no more data
  
  const [status, setStatus] = useState<'loading' | 'ready' | 'empty' | 'error'>('loading');

  // Helper: apply realtime price into current bar (1m or 1d aligned)
  const applyRealtime = useCallback((price: number, tsMs?: number) => {
    if (!seriesRef.current || typeof price !== 'number') return;
    const nowMs = typeof tsMs === 'number' ? tsMs : Date.now();
    const lastBar = allDataRef.current[allDataRef.current.length - 1];

    // Compute bar start time by interval, aligning daily bars to KST midnight
    const sec = Math.floor(nowMs / 1000);
    let newBarTime = sec - (sec % 60); // default minute alignment
    if (interval === '1d') {
      const KST_OFFSET = 9 * 60 * 60; // seconds
      const kstSec = sec + KST_OFFSET;
      const kstDayStart = kstSec - (kstSec % 86400);
      newBarTime = kstDayStart - KST_OFFSET;
    }

    if (!lastBar || newBarTime > (lastBar.time as number)) {
      const newBar: any = { time: newBarTime as UTCTimestamp };
      if (chartType === 'area') {
        newBar.value = price;
      } else {
        newBar.open = price;
        newBar.high = price;
        newBar.low = price;
        newBar.close = price;
      }
      seriesRef.current.update(newBar);
      allDataRef.current.push(newBar);
    } else {
      const updatedBar: any = { ...lastBar };
      if (chartType === 'area') {
        updatedBar.value = price;
      } else {
        updatedBar.high = Math.max(lastBar.high, price);
        updatedBar.low = Math.min(lastBar.low, price);
        updatedBar.close = price;
      }
      seriesRef.current.update(updatedBar);
      allDataRef.current[allDataRef.current.length - 1] = updatedBar;
    }
  }, [interval, chartType]);

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
    allDataRef.current = []; // Reset data for new range
    
    // Calculate 'after' timestamp based on KST (UTC+9)
    const now = new Date();
    // KST Offset: +9 hours
    const KST_OFFSET = 9 * 60 * 60 * 1000;
    const nowKst = new Date(now.getTime() + KST_OFFSET);
    
    let fromTime = new Date();
    let limit = 15000;

    switch (range) {
        case '1D':
            // Start of Today KST (00:00 KST)
            // Calculate KST midnight using UTC components of the shifted KST date
            const kstMidnight = new Date(Date.UTC(
                nowKst.getUTCFullYear(), 
                nowKst.getUTCMonth(), 
                nowKst.getUTCDate(), 
                0, 0, 0
            ));
            // Convert back to absolute time (UTC) by subtracting offset
            fromTime = new Date(kstMidnight.getTime() - KST_OFFSET);
            break;
        case '1W':
            fromTime.setDate(now.getDate() - 7);
            break;
        case '3M':
            fromTime.setMonth(now.getMonth() - 3);
            break;
        case '1Y':
            fromTime.setFullYear(now.getFullYear() - 1);
            break;
        case '5Y':
            fromTime.setFullYear(now.getFullYear() - 5);
            break;
    }

    try {
      // console.log(`[CandleChart] Loading data for ${tickerId} (${range}) from ${fromTime.toISOString()}`);
      
      const data = await api.get(`market/candles/${tickerId}`, {
        searchParams: { 
            interval, 
            limit,
            after: fromTime.toISOString() 
        }
      }).json<CandleData[]>();

      if (!seriesRef.current) return;

      if (data.length > 0) {
        const formatted = transformData(data);
        const unique = formatted.filter((v, i, a) => a.findIndex(t => t.time === v.time) === i);
        
        seriesRef.current.setData(unique);
        allDataRef.current = unique;
        earliestTimestamp.current = data[0].timestamp;

        if (chartRef.current) {
            // Auto-fit content to show exactly the loaded period
            chartRef.current.timeScale().fitContent();
        }
        setStatus('ready');

        // Immediately reflect current price if available to avoid stale last bar
        if (typeof rtPrice === 'number') {
          applyRealtime(rtPrice, rtTimestamp);
        }
      } else {
        // console.warn("[CandleChart] No data found.");
        setStatus('empty');
        hasMoreHistory.current = false;
      }
    } catch (err) {
      console.error("[CandleChart] Failed to load initial data", err);
      setStatus('error');
    }
  }, [tickerId, range, interval, transformData, applyRealtime]);

  // Load Historical Data
  const loadMoreHistory = useCallback(async () => {
    if (isFetchingHistory.current) return;
    if (!hasMoreHistory.current) return; // Don't fetch if known empty
    if (!earliestTimestamp.current) return;
    if (!seriesRef.current) return;

    isFetchingHistory.current = true;
    
    try {
      const data = await api.get(`market/candles/${tickerId}`, {
        searchParams: { 
            interval, 
            limit: 300,
            before: earliestTimestamp.current
        }
      }).json<CandleData[]>();

      if (data.length > 0) {
        const formatted = transformData(data);
        const uniqueNew = formatted.filter(n => !allDataRef.current.some(e => e.time === n.time));
        
        if (uniqueNew.length > 0) {
            const merged = [...uniqueNew, ...allDataRef.current];
            seriesRef.current.setData(merged);
            allDataRef.current = merged;
            earliestTimestamp.current = data[0].timestamp;
        }
        
        if (data.length < 300) {
            hasMoreHistory.current = false;
        }

      } else {
          hasMoreHistory.current = false;
      }
    } catch (err) {
      console.error("[CandleChart] Failed to load history", err);
    } finally {
      isFetchingHistory.current = false;
    }
  }, [tickerId, interval, transformData]);

  // Real-time Update (from props)
  useEffect(() => {
    if (typeof rtPrice !== 'number') return;
    applyRealtime(rtPrice, rtTimestamp);
  }, [rtPrice, rtTimestamp, applyRealtime]);

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
        tickMarkFormatter: (timestamp: number) => {
            // Force KST display for axis labels
            const date = new Date(timestamp * 1000);
            const options: Intl.DateTimeFormatOptions = { timeZone: 'Asia/Seoul', hour12: false };

            switch(range) {
                case '1D':
                    options.hour = '2-digit'; options.minute = '2-digit';
                    return date.toLocaleTimeString('ko-KR', options); // Time only
                case '1W':
                    // MM.dd HH:mm
                    return `${date.toLocaleDateString('ko-KR', {timeZone: 'Asia/Seoul', month:'numeric', day:'numeric'})} ${date.toLocaleTimeString('ko-KR', {timeZone: 'Asia/Seoul', hour:'2-digit', minute:'2-digit', hour12:false})}`;
                case '3M':
                case '1Y':
                    options.month = 'numeric'; options.day = 'numeric';
                    return date.toLocaleDateString('ko-KR', options);
                case '5Y':
                    options.year = 'numeric'; options.month = 'numeric'; options.day = 'numeric';
                    return date.toLocaleDateString('ko-KR', options);
                default:
                    return date.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' });
            }
        },
      },
      rightPriceScale: {
        borderColor: '#314368',
      },
      leftPriceScale: {
        visible: true,
        borderColor: '#314368',
      },
      // Localization for KST (Tooltip)
      localization: {
        locale: 'ko-KR',
        dateFormat: 'yyyy-MM-dd',
        timeFormatter: (timestamp: number) => {
            const date = new Date(timestamp * 1000);
            const options: Intl.DateTimeFormatOptions = { timeZone: 'Asia/Seoul', hour12: false };
            
            switch(range) {
                case '1D':
                    options.hour = '2-digit'; options.minute = '2-digit';
                    break;
                case '1W':
                    options.month = 'numeric'; options.day = 'numeric'; options.hour = '2-digit'; options.minute = '2-digit';
                    break;
                case '3M':
                case '1Y':
                    options.month = 'numeric'; options.day = 'numeric';
                    break;
                case '5Y':
                    options.year = 'numeric'; options.month = 'numeric'; options.day = 'numeric';
                    break;
                default:
                    options.hour = '2-digit'; options.minute = '2-digit';
            }
            return date.toLocaleString('ko-KR', options);
        },
      },
      // Disable scrolling and zooming for fixed view
      handleScale: {
        mouseWheel: false,
        pinch: false,
        axisPressedMouseMove: false,
      },
      handleScroll: {
        mouseWheel: false,
        pressedMouseMove: false,
        horzTouchDrag: false,
        vertTouchDrag: false,
      },
      kineticScroll: {
        touch: false,
        mouse: false,
      },
    });

    let series: ISeriesApi<"Candlestick" | "Area">;

    const digits = getCurrencyDigits(currencyCode);
    if (chartType === 'area') {
      series = chart.addSeries(AreaSeries, {
            topColor: 'rgba(13, 89, 242, 0.4)', // Brand Primary with opacity
            bottomColor: 'rgba(13, 89, 242, 0)',
            lineColor: '#0d59f2',
            lineWidth: 2,
        priceFormat: { 
            type: 'custom', 
            minMove: Math.pow(10, -digits),
            formatter: (p: number) => formatCurrencyDisplay(p, currencyCode, 'ROUND_DOWN')
        },
        });
    } else {
      series = chart.addSeries(CandlestickSeries, {
              upColor: '#ef4444', // profit (red)
              downColor: '#0ea5e9', // loss (blue)
              borderVisible: false,
              wickUpColor: '#ef4444',
              wickDownColor: '#0ea5e9',
          priceFormat: { 
            type: 'custom', 
            minMove: Math.pow(10, -digits),
            formatter: (p: number) => formatCurrencyDisplay(p, currencyCode, 'ROUND_DOWN')
          },
        });
    }

    chartRef.current = chart;
    seriesRef.current = series;

    loadInitialData();

    // Only enable infinite scroll if chart is interactive (which is not now)
    // Keeping logic here in case we re-enable interactions later, but it won't trigger if scroll is disabled
    const handleVisibleLogicalRangeChange = (range: LogicalRange | null) => {
        if (range) {
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
  }, [loadInitialData, loadMoreHistory, chartType, range]);

  return (
    <div className="w-full h-full relative group">
      <div ref={chartContainerRef} className="w-full h-full" />
      
      {/* Status Overlay */}
      {status !== 'ready' && (
        <div className="absolute inset-0 flex items-center justify-center bg-[#101623]/80 z-10 pointer-events-none">
            {status === 'loading' && <Skeleton className="w-full h-full" />}
            {status === 'empty' && <span className="text-[#90a4cb]">No Data Available</span>}
            {status === 'error' && <span className="text-red-500">Failed to Load Chart</span>}
        </div>
      )}
    </div>
  );
};
