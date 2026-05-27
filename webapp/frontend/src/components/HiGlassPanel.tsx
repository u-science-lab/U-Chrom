import React, { useEffect, useRef, useState } from 'react';

interface HiGlassPanelProps {
  width?: number;
  height?: number;
  chromName?: string;
  startBin?: number;
  endBin?: number;
  resolution?: number;
  onViewportChange?: (viewportInfo: { chromName: string; startBin: number; endBin: number }) => void;
}

const HiGlassPanel: React.FC<HiGlassPanelProps> = ({
  width = 800,
  height = 400,
  chromName = 'chr1',
  startBin,
  endBin,
  resolution = 25000,
  onViewportChange,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const hgRef = useRef<any>(null);
  const [isLoaded, setIsLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tilesetInfo, setTilesetInfo] = useState<any>(null);

  // Fetch tileset info from backend
  useEffect(() => {
    const fetchTilesetInfo = async () => {
      try {
        const response = await fetch('/api/higlass/tileset_info/?d=uchrom-contact');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        setTilesetInfo(data);
      } catch (err) {
        console.warn('HiGlass tileset info fetch failed:', err);
        // Not fatal - HiGlass can still load without pre-fetched info
      }
    };
    fetchTilesetInfo();
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;

    let mounted = true;

    const initHiGlass = async () => {
      try {
        // Dynamic import to avoid SSR issues
        const hglib = await import('higlass');

        if (!mounted || !containerRef.current) return;

        const viewConfig = {
          editable: true,
          zoomFixed: false,
          trackSourceServers: ['/api/higlass'],
          exportViewUrl: '/api/higlass/viewconfs',
          views: [
            {
              uid: 'main-view',
              initialXDomain: startBin && endBin
                ? [startBin, endBin]
                : [0, 1000000],
              initialYDomain: [0, 1000000],
              tracks: {
                top: [
                  {
                    uid: 'chromosome-labels',
                    type: 'horizontal-chromosome-labels',
                    height: 30,
                    options: {
                      color: '#777777',
                      stroke: '#ffffff',
                      fontSize: 12,
                      fontIsLeftAligned: false,
                    },
                  },
                ],
                center: [
                  {
                    uid: 'heatmap-track',
                    type: 'heatmap',
                    server: '/api/higlass',
                    tilesetUid: 'uchrom-contact',
                    height: height - 60,
                    options: {
                      colorRange: [
                        'white',
                        'rgba(245,166,35,1.0)',
                        'rgba(208,2,27,1.0)',
                        'black',
                      ],
                      maxZoom: null,
                      labelPosition: 'bottomLeft',
                      name: 'U-Chrom Contact Map',
                    },
                  },
                ],
                left: [],
                right: [],
                bottom: [],
                whole: [],
                gallery: [],
              },
              layout: {
                w: 12,
                h: 12,
                x: 0,
                y: 0,
              },
            },
          ],
          zoomLocks: { locksByViewUid: {}, locksDict: {} },
          locationLocks: { locksByViewUid: {}, locksDict: {} },
          valueScaleLocks: { locksByViewUid: {}, locksDict: {} },
        };

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const api: any = await hglib.viewer(containerRef.current, viewConfig, {
          bounded: true,
        });

        hgRef.current = api;
        setIsLoaded(true);

        // Subscribe to location changes for 1D-3D sync
        if (onViewportChange) {
          api.on('location', (event: any) => {
            const { xDomain } = event;
            if (xDomain && onViewportChange) {
              onViewportChange({
                chromName,
                startBin: Math.floor(xDomain[0] / resolution),
                endBin: Math.ceil(xDomain[1] / resolution),
              });
            }
          });
        }
      } catch (err: any) {
        if (mounted) {
          console.error('HiGlass initialization failed:', err);
          setError(err.message || 'Failed to initialize HiGlass');
        }
      }
    };

    initHiGlass();

    return () => {
      mounted = false;
      if (hgRef.current) {
        try {
          hgRef.current.destroy?.();
        } catch (e) {
          // ignore cleanup errors
        }
        hgRef.current = null;
      }
    };
  }, []); // Only init once

  // Navigate to a specific region when props change
  useEffect(() => {
    if (!hgRef.current || !isLoaded || startBin === undefined || endBin === undefined) return;

    try {
      hgRef.current.zoomTo('main-view', startBin * resolution, endBin * resolution, 0, 0, 500);
    } catch (e) {
      console.warn('HiGlass zoom failed:', e);
    }
  }, [startBin, endBin, resolution, isLoaded]);

  if (error) {
    return (
      <div
        style={{
          width,
          height,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#1a1a2e',
          color: '#ff6b6b',
          border: '1px solid #333',
          borderRadius: 4,
          flexDirection: 'column',
          gap: 8,
        }}
      >
        <div style={{ fontSize: 14, fontWeight: 'bold' }}>HiGlass Error</div>
        <div style={{ fontSize: 12, opacity: 0.8 }}>{error}</div>
        <div style={{ fontSize: 11, opacity: 0.6 }}>
          Check that Hi-C data is loaded and backend is running
        </div>
      </div>
    );
  }

  return (
    <div style={{ position: 'relative', width, height }}>
      {!isLoaded && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: '#1a1a2e',
            color: '#888',
            fontSize: 13,
            zIndex: 10,
          }}
        >
          Loading HiGlass...
        </div>
      )}
      <div
        ref={containerRef}
        style={{
          width: '100%',
          height: '100%',
          background: '#1a1a2e',
        }}
      />
    </div>
  );
};

export default HiGlassPanel;
