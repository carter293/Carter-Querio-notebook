import { useEffect, useRef } from 'react';
import { Output, TableData } from '../api-client';
import embed from 'vega-embed';
import type { VisualizationSpec } from 'vega-embed';
import Plot from 'react-plotly.js';
import type { Data, Layout, Config } from 'plotly.js';

interface OutputRendererProps {
  output: Output;
  cellId?: string;
  outputIndex?: number;
}

// PlotlySpec interface - must be defined before the type guard
interface PlotlySpec {
  data: Data[];
  layout?: Partial<Layout>;
  config?: Partial<Config>;
}

// Type guard for TableData
function isTableData(data: unknown): data is TableData {
  return (
    typeof data === 'object' &&
    data !== null &&
    'type' in data &&
    data.type === 'table' &&
    'columns' in data &&
    'rows' in data
  );
}

// Type guard for PlotlySpec
function isPlotlySpec(data: unknown): data is PlotlySpec {
  return (
    typeof data === 'object' &&
    data !== null &&
    'data' in data &&
    Array.isArray((data as { data: unknown }).data)
  );
}

export function OutputRenderer({ output, cellId, outputIndex }: OutputRendererProps) {
  switch (output.mime_type) {
    case 'image/png':
      if (typeof output.data !== 'string') {
        return <div className="text-error">Error: Expected base64 string for PNG image</div>;
      }
      return (
        <img
          src={`data:image/png;base64,${output.data}`}
          alt="Chart output"
          className="max-w-full h-auto"
        />
      );

    case 'text/html':
      if (typeof output.data !== 'string') {
        return <div className="text-error">Error: Expected HTML string</div>;
      }
      return (
        <div
          dangerouslySetInnerHTML={{ __html: output.data }}
          className="w-full"
        />
      );

    case 'application/vnd.vegalite.v6+json':
      if (typeof output.data === 'object' && output.data !== null) {
        return <VegaLiteRenderer spec={output.data as VisualizationSpec} />;
      }
      return <div className="text-error">Error: Expected Vega-Lite spec object</div>;

    case 'application/vnd.plotly.v1+json':
      if (isPlotlySpec(output.data)) {
        return <PlotlyRenderer spec={output.data} cellId={cellId} outputIndex={outputIndex} />;
      }
      return <div className="text-error">Error: Expected Plotly spec object</div>;

    case 'application/json':
      if (isTableData(output.data)) {
        return (
          <div className="table-container">
            <table className="table">
              <thead className="table-header">
                <tr>
                  {output.data.columns.map((col: string) => (
                    <th key={col} className="table-th">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {output.data.rows.map((row: Array<string | number | boolean | null>, idx: number) => (
                  <tr key={idx} className="table-row-hover">
                    {row.map((val: string | number | boolean | null, i: number) => (
                      <td key={i} className="table-td">
                        {val === null ? (
                          <span className="text-null">null</span>
                        ) : (
                          String(val)
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
      return <pre className="output-json">{JSON.stringify(output.data, null, 2)}</pre>;

    case 'text/plain':
      if (typeof output.data !== 'string') {
        return <div className="text-error">Error: Expected string for plain text</div>;
      }
      return (
        <pre className="output-pre">
          {output.data}
        </pre>
      );

    default:
      return (
        <div className="text-helper">
          Unsupported output type: {output.mime_type}
        </div>
      );
  }
}

interface VegaLiteRendererProps {
  spec: VisualizationSpec;
}

function VegaLiteRenderer({ spec }: VegaLiteRendererProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      embed(containerRef.current, spec, {
        actions: false,
        renderer: 'svg'
      }).catch(err => {
        console.error('Vega-Lite rendering error:', err);
      });
    }
  }, [spec]);

  return <div ref={containerRef} className="w-full" />;
}

interface PlotlyRendererProps {
  spec: PlotlySpec;
  cellId?: string;
  outputIndex?: number;
}

function PlotlyRenderer({ spec, cellId, outputIndex }: PlotlyRendererProps) {
  // Create a unique key that changes when the data changes to force remount
  // This ensures the Plot component properly unmounts and remounts when cell re-executes
  const plotKey = cellId && outputIndex !== undefined 
    ? `${cellId}-${outputIndex}-${JSON.stringify(spec.data).slice(0, 100)}`
    : `plot-${JSON.stringify(spec.data).slice(0, 100)}`;

  // Use user-provided dimensions or defaults
  // Fixed dimensions prevent Plotly's .svg-container from collapsing to height: 100%
  // during React re-renders, which causes DOM shifting
  const height = spec.layout?.height || 500;

  const layout = {
    ...spec.layout,
    height,
  };

  return (
    <div className="w-full" style={{ minHeight: `${height}px` }}>
      <Plot
        key={plotKey}
        data={spec.data}
        layout={layout}
        config={{ 
          autosizable: true,
          responsive: true,
          displayModeBar: true 
        }}
        style={{ width: '100%' }}
        useResizeHandler={true}
      />
    </div>
  );
}
