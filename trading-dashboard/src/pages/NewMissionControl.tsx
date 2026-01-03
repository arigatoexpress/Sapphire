import React from 'react';
import { Grid, Box } from '@mui/material';
import { MissionControlLayout } from '../components/mission-control/layout/MissionControlLayout';
import { NewAsterAgentGrid } from '../components/mission-control/NewAsterAgentGrid';
import { NewAsterBrainStream } from '../components/mission-control/NewAsterBrainStream';
import UnifiedPositionsTable from '../components/UnifiedPositionsTable'; // Legacy for now, needs context wiring
import { NeuralConsensus } from '../components/mission-control/NeuralConsensus';
import { useTradingData } from '../contexts/TradingContext';
import PlatformRouterStatus from '../components/PlatformRouterStatus';
import TradeExecutionPanel from '../components/TradeExecutionPanel';

// Wrapper for Legacy Position Table to use Context Data
const ConnectedPositionsTable = () => {
    const { open_positions } = useTradingData();
    const asterPositions = open_positions; // All positions are Aster now

    return (
        <UnifiedPositionsTable
            asterPositions={asterPositions as any}
            hypePositions={[]} // Empty array for legacy prop
            onUpdateTpSl={(sym, tp, sl) => console.log('TP/SL Update Placeholder', sym, tp, sl)}
        />
    );
};

const NewMissionControl: React.FC = () => {
    return (
        <MissionControlLayout>
            {/* Platform Router Status - Full Width Header */}
            <Box sx={{ mb: 3 }}>
                <PlatformRouterStatus />
            </Box>

            <Grid container spacing={3}>
                {/* LEFT COLUMN: AGENTS & POSITIONS */}
                <Grid item xs={12} lg={7}>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                        <NewAsterAgentGrid />
                        <ConnectedPositionsTable />
                    </Box>
                </Grid>

                {/* RIGHT COLUMN: BRAIN STREAM, CONSENSUS, EXECUTIONS */}
                <Grid item xs={12} lg={5}>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, height: '100%', overflow: 'hidden' }}>
                        <NewAsterBrainStream />
                        <NeuralConsensus />
                        <TradeExecutionPanel />
                    </Box>
                </Grid>
            </Grid>
        </MissionControlLayout>
    );
};

export default NewMissionControl;
