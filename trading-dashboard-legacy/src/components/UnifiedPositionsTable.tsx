import React, { useState } from 'react';
import {
    Box,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Paper,
    Typography,
    Chip,
    IconButton,
    Button,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    TextField,
    Tabs,
    Tab
} from '@mui/material';
import EditIcon from '@mui/icons-material/Edit';
import { alpha } from '@mui/material/styles';

interface Position {
    symbol: string;
    side: 'BUY' | 'SELL';
    size: number;
    entryPrice: number;
    currentPrice: number;
    pnl: number;
    pnlPercent: number;
    tp?: number;
    sl?: number;
    system: 'ASTER' | 'HYPERLIQUID';
}

interface UnifiedPositionsTableProps {
    asterPositions: Position[];
    hypePositions: Position[];
    onUpdateTpSl: (symbol: string, tp: number | null, sl: number | null) => void;
}

const UnifiedPositionsTable: React.FC<UnifiedPositionsTableProps> = ({ asterPositions, hypePositions, onUpdateTpSl }) => {
    const [tab, setTab] = useState(0); // 0 = ALL, 1 = ASTER, 2 = HYPE
    const [editPos, setEditPos] = useState<Position | null>(null);
    const [newTp, setNewTp] = useState<string>('');
    const [newSl, setNewSl] = useState<string>('');

    const allPositions = [...asterPositions, ...hypePositions];
    const displayPositions = tab === 0 ? allPositions :
        tab === 1 ? asterPositions : hypePositions;

    const handleEditClick = (pos: Position) => {
        setEditPos(pos);
        setNewTp(pos.tp?.toString() || '');
        setNewSl(pos.sl?.toString() || '');
    };

    const handleSave = () => {
        if (editPos) {
            onUpdateTpSl(editPos.symbol, newTp ? parseFloat(newTp) : null, newSl ? parseFloat(newSl) : null);
            setEditPos(null);
        }
    };

    return (
        <Paper
            elevation={0}
            sx={{
                bgcolor: '#0a0b10',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: 2,
                overflow: 'hidden'
            }}
        >
            <Box sx={{ borderBottom: 1, borderColor: 'divider', px: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Tabs value={tab} onChange={(_, v) => setTab(v)} textColor="inherit" indicatorColor="secondary">
                    <Tab label="ALL POSITIONS" sx={{ fontWeight: 700, fontSize: '0.8rem' }} />
                    <Tab label="ASTER (SWARM)" sx={{ fontWeight: 700, fontSize: '0.8rem', color: tab === 1 ? '#00d4aa' : undefined }} />
                    <Tab label="HYPERLIQUID (HFT)" sx={{ fontWeight: 700, fontSize: '0.8rem', color: tab === 2 ? '#8a2be2' : undefined }} />
                </Tabs>
            </Box>

            <TableContainer sx={{ maxHeight: 400 }}>
                <Table stickyHeader size="small">
                    <TableHead>
                        <TableRow>
                            <TableCell sx={{ bgcolor: '#0f111a', color: '#666', borderBottom: '1px solid #333' }}>SYSTEM</TableCell>
                            <TableCell sx={{ bgcolor: '#0f111a', color: '#666', borderBottom: '1px solid #333' }}>SYMBOL</TableCell>
                            <TableCell sx={{ bgcolor: '#0f111a', color: '#666', borderBottom: '1px solid #333' }}>SIDE</TableCell>
                            <TableCell sx={{ bgcolor: '#0f111a', color: '#666', borderBottom: '1px solid #333', textAlign: 'right' }}>SIZE</TableCell>
                            <TableCell sx={{ bgcolor: '#0f111a', color: '#666', borderBottom: '1px solid #333', textAlign: 'right' }}>ENTRY</TableCell>
                            <TableCell sx={{ bgcolor: '#0f111a', color: '#666', borderBottom: '1px solid #333', textAlign: 'right' }}>PRICE</TableCell>
                            <TableCell sx={{ bgcolor: '#0f111a', color: '#666', borderBottom: '1px solid #333', textAlign: 'right' }}>PnL</TableCell>
                            <TableCell sx={{ bgcolor: '#0f111a', color: '#666', borderBottom: '1px solid #333', textAlign: 'center' }}>TP / SL</TableCell>
                            <TableCell sx={{ bgcolor: '#0f111a', color: '#666', borderBottom: '1px solid #333' }}></TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {displayPositions.map((pos) => (
                            <TableRow key={`${pos.system}-${pos.symbol}`} sx={{ '&:hover': { bgcolor: alpha('#fff', 0.05) } }}>
                                <TableCell>
                                    <Chip
                                        label={pos.system}
                                        size="small"
                                        sx={{
                                            height: 20,
                                            fontSize: '0.65rem',
                                            bgcolor: pos.system === 'ASTER' ? alpha('#00d4aa', 0.1) : alpha('#8a2be2', 0.1),
                                            color: pos.system === 'ASTER' ? '#00d4aa' : '#8a2be2',
                                            border: `1px solid ${pos.system === 'ASTER' ? alpha('#00d4aa', 0.3) : alpha('#8a2be2', 0.3)}`
                                        }}
                                    />
                                </TableCell>
                                <TableCell sx={{ fontWeight: 700, color: '#fff' }}>{pos.symbol}</TableCell>
                                <TableCell>
                                    <span style={{ color: pos.side === 'BUY' ? '#00ff00' : '#ff0000', fontWeight: 700 }}>
                                        {pos.side}
                                    </span>
                                </TableCell>
                                <TableCell sx={{ textAlign: 'right', color: '#ccc', fontFamily: 'Monospace' }}>{pos.size}</TableCell>
                                <TableCell sx={{ textAlign: 'right', color: '#ccc', fontFamily: 'Monospace' }}>${pos.entryPrice}</TableCell>
                                <TableCell sx={{ textAlign: 'right', color: '#fff', fontFamily: 'Monospace' }}>${pos.currentPrice}</TableCell>
                                <TableCell sx={{ textAlign: 'right', fontFamily: 'Monospace' }}>
                                    <span style={{ color: (Number(pos.pnl) || 0) >= 0 ? '#00ff00' : '#ff0000' }}>
                                        {(Number(pos.pnl) || 0) >= 0 ? '+' : ''}{(Number(pos.pnl) || 0).toFixed(2)} ({(Number(pos.pnlPercent) || 0).toFixed(2)}%)
                                    </span>
                                </TableCell>
                                <TableCell sx={{ textAlign: 'center' }}>
                                    <Box sx={{ display: 'flex', gap: 1, justifyContent: 'center' }}>
                                        {pos.tp && <Chip label={`TP: ${pos.tp}`} size="small" variant="outlined" sx={{ color: '#00ff00', borderColor: '#00ff00', fontSize: '0.7rem' }} />}
                                        {pos.sl && <Chip label={`SL: ${pos.sl}`} size="small" variant="outlined" sx={{ color: '#ff0000', borderColor: '#ff0000', fontSize: '0.7rem' }} />}
                                    </Box>
                                </TableCell>
                                <TableCell>
                                    <IconButton size="small" onClick={() => handleEditClick(pos)} sx={{ color: '#aaa' }}>
                                        <EditIcon fontSize="small" />
                                    </IconButton>
                                </TableCell>
                            </TableRow>
                        ))}
                        {displayPositions.length === 0 && (
                            <TableRow>
                                <TableCell colSpan={9} sx={{ textAlign: 'center', py: 4, color: '#666' }}>
                                    NO ACTIVE POSITIONS
                                </TableCell>
                            </TableRow>
                        )}
                    </TableBody>
                </Table>
            </TableContainer>

            {/* Edit Dialog */}
            <Dialog open={!!editPos} onClose={() => setEditPos(null)} PaperProps={{ sx: { bgcolor: '#1e1e24', color: '#fff' } }}>
                <DialogTitle>Adjust TP/SL for {editPos?.symbol}</DialogTitle>
                <DialogContent>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1, minWidth: 300 }}>
                        <TextField
                            label="Take Profit"
                            value={newTp}
                            onChange={(e) => setNewTp(e.target.value)}
                            fullWidth
                            variant="outlined"
                            InputProps={{ style: { color: '#00ff00' } }}
                            InputLabelProps={{ style: { color: '#aaa' } }}
                            sx={{ '& .MuiOutlinedInput-root': { '& fieldset': { borderColor: '#333' } } }}
                        />
                        <TextField
                            label="Stop Loss"
                            value={newSl}
                            onChange={(e) => setNewSl(e.target.value)}
                            fullWidth
                            variant="outlined"
                            InputProps={{ style: { color: '#ff0000' } }}
                            InputLabelProps={{ style: { color: '#aaa' } }}
                            sx={{ '& .MuiOutlinedInput-root': { '& fieldset': { borderColor: '#333' } } }}
                        />
                    </Box>
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setEditPos(null)} sx={{ color: '#aaa' }}>Cancel</Button>
                    <Button onClick={handleSave} variant="contained" color="secondary">Save Changes</Button>
                </DialogActions>
            </Dialog>
        </Paper>
    );
};

export default UnifiedPositionsTable;
