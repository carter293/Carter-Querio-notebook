import React, { useEffect, useRef } from 'react';
import { Output, TableData } from '../api';
import embed from 'vega-embed';
import type { VisualizationSpec } from 'vega-embed';

interface OutputRendererProps {
  output: Output;
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

export function OutputRenderer({ output }: OutputRendererProps) {
  switch (output.mime_type) {
    case 'image/png':
      if (typeof output.data !== 'string') {
        return <div>Error: Expected base64 string for PNG image</div>;
      }
      return (
        <img
          src={`data:image/png;base64,${output.data}`}
          alt="Chart output"
          style={{ maxWidth: '100%', height: 'auto' }}
        />
      );

    case 'text/html':
      if (typeof output.data !== 'string') {
        return <div>Error: Expected HTML string</div>;
      }
      return (
        <div
          dangerouslySetInnerHTML={{ __html: output.data }}
          style={{ width: '100%' }}
        />
      );

    case 'application/vnd.vegalite.v5+json':
      if (typeof output.data === 'object' && output.data !== null) {
        return <VegaLiteRenderer spec={output.data as VisualizationSpec} />;
      }
      return <div>Error: Expected Vega-Lite spec object</div>;

    case 'application/json':
      if (isTableData(output.data)) {
        return (
          <table style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '12px'
          }}>
            <thead>
              <tr style={{ backgroundColor: '#e5e7eb' }}>
                {output.data.columns.map((col) => (
                  <th key={col} style={{
                    border: '1px solid #d1d5db',
                    padding: '4px 8px',
                    textAlign: 'left'
                  }}>{col}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {output.data.rows.map((row, idx) => (
                <tr key={idx}>
                  {row.map((val, i) => (
                    <td key={i} style={{
                      border: '1px solid #d1d5db',
                      padding: '4px 8px'
                    }}>{val === null ? 'null' : String(val)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        );
      }
      return <pre>{JSON.stringify(output.data, null, 2)}</pre>;

    case 'text/plain':
      if (typeof output.data !== 'string') {
        return <div>Error: Expected string for plain text</div>;
      }
      return (
        <pre style={{
          backgroundColor: '#f3f4f6',
          padding: '8px',
          borderRadius: '4px',
          fontSize: '13px',
          overflow: 'auto',
          whiteSpace: 'pre-wrap'
        }}>
          {output.data}
        </pre>
      );

    default:
      return (
        <div style={{ color: '#6b7280', fontSize: '12px' }}>
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

  return <div ref={containerRef} style={{ width: '100%' }} />;
}
