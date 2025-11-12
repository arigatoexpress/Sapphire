import { type User } from 'firebase/auth';
import { type CommunityComment } from '../services/community';
declare const useCommunityComments: (user: User | null) => [CommunityComment[], (message: string) => Promise<void>, boolean];
export type { CommunityComment };
export default useCommunityComments;
