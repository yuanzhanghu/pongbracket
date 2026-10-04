import { ScrollArea, Table } from '@mantine/core';

export default function TableLayoutLarge({ children }: any) {
  return (
    <>
      <ScrollArea>
        {/* Default (7px) vertical spacing — same row height as the plain
            Mantine table in the participants tab. */}
        <Table horizontalSpacing="md" striped highlightOnHover style={{ fontSize: 'inherit' }}>
          {children}
        </Table>
      </ScrollArea>
    </>
  );
}
